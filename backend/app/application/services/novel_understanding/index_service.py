"""Incremental chapter understanding and index checkpoint orchestration."""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.domain.entities.novel import (
    EventType,
    NovelEntity,
    NovelEvent,
    NovelRelationship,
    NovelStateChange,
    RelationType,
    StateField,
)
from app.domain.entities.novel_runtime import NovelIndexState
from app.domain.repositories.vector_store import VectorRecord

from .auto_extractor import AutoExtractor
from .bm25_index import BM25Index
from .embedding import EmbeddingAdapter, EmbeddingUnavailable


@dataclass
class IndexResult:
    owner_scope: str
    book_id: int
    processed_chapters: int = 0
    skipped_chapters: int = 0
    failed_chapters: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    indexed_chapters: list[int] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.failed_chapters == 0


class NovelIndexService:
    """Run deterministic extraction first and keep each chapter resumable."""

    def __init__(
        self,
        repo,
        *,
        extractor: AutoExtractor | None = None,
        structured_extractor=None,
        embedding: EmbeddingAdapter | None = None,
        vector_store=None,
        bm25_index: BM25Index | None = None,
        knowledge_version: str = "v2-local-evidence",
        prompt_version: str = "",
        toolset_version: str = "",
        embedding_model: str = "",
        embedding_dimension: int = 0,
    ):
        self.repo = repo
        self.extractor = extractor or AutoExtractor()
        self.structured_extractor = structured_extractor
        self.embedding = embedding
        self.vector_store = vector_store
        self.bm25_index = bm25_index
        self.knowledge_version = knowledge_version
        self.prompt_version = prompt_version
        self.toolset_version = toolset_version
        self.embedding_model = embedding_model or str(getattr(embedding, "model", "") or "")
        self.embedding_dimension = int(embedding_dimension or 0)
        self._bm25_indexes: dict[tuple[str, int, str], BM25Index] = {}
        self._relationship_keys: dict[tuple[str, int], set[tuple]] = {}
        self._event_keys: dict[tuple[str, int], set[tuple]] = {}
        self._state_keys: dict[tuple[str, int], set[tuple]] = {}

    async def index_book(
        self,
        owner_scope: str,
        book_id: int,
        from_chapter: int | None = None,
    ) -> IndexResult:
        result = IndexResult(owner_scope=owner_scope, book_id=int(book_id))
        chapters = await self._chapters(owner_scope, book_id, from_chapter)
        if not chapters:
            return result

        bm25 = self.bm25_index or self._bm25_indexes.setdefault(
            (owner_scope, int(book_id), self.knowledge_version), BM25Index()
        )
        bm25.clear()
        for chapter in chapters:
            bm25.add_document(chapter.id, self._chapter_index_text(chapter))
        bm25.build()

        for chapter in chapters:
            content = chapter.raw_text or ""
            content_hash = chapter.raw_text_hash or self._hash(content)
            state = await self.repo.get_index_state(owner_scope, book_id, chapter.id)
            if self._can_skip(state, content_hash):
                result.skipped_chapters += 1
                continue

            state = NovelIndexState(
                owner_scope=owner_scope,
                book_id=int(book_id),
                chapter_id=chapter.id,
                content_hash=content_hash,
                knowledge_version=self.knowledge_version,
                extraction_status="running",
                bm25_status="completed",
                vector_status="disabled",
                embedding_model=self.embedding_model,
                embedding_dimension=self.embedding_dimension,
            )
            await self.repo.save_index_state(state)
            try:
                entities, relationships, structured = await self._extract(chapter)
                structured_status = "not_requested"
                try:
                    if structured is not None and self.structured_extractor is not None:
                        structured_status = "completed"
                        structured = await self._validate_structured(structured, chapter)
                    elif structured is None:
                        structured_status = "not_requested"
                except Exception as exc:
                    # Local extraction remains usable when only the optional
                    # structured payload is malformed.  Keep the failure in
                    # the snapshot so a later retry can target that portion.
                    structured = None
                    structured_status = "failed"
                    state.failure_reason = f"structured extraction: {str(exc)[:450]}"
                    result.errors.append({"chapter_id": chapter.id, "error": str(exc)[:500], "scope": "structured"})

                structured_relationships, structured_events, structured_states = self._structured_entities(
                    structured,
                    chapter.book_id,
                    chapter_num=chapter.canonical_num,
                )
                snapshot = self._chapter_snapshot(
                    chapter,
                    entities=list(entities or []),
                    relationships=list(relationships or []) + structured_relationships,
                    events=structured_events,
                    state_changes=structured_states,
                    structured_status=structured_status,
                )
                state.extraction_payload = snapshot
                state.extraction_status = "completed"
                state.bm25_status = "completed"
                await self._index_vector(owner_scope, chapter, state)
                state.last_success_at = datetime.now(timezone.utc)
                if structured_status != "failed":
                    state.failure_reason = ""
                await self.repo.save_index_state(state)
                result.processed_chapters += 1
                result.indexed_chapters.append(int(chapter.id))
            except Exception as exc:
                state.extraction_status = "failed"
                state.failure_reason = str(exc)[:500]
                await self.repo.save_index_state(state)
                result.failed_chapters += 1
                result.errors.append({"chapter_id": chapter.id, "error": str(exc)[:500]})
        await self._rebuild_knowledge(owner_scope, book_id)
        return result

    async def _chapters(self, owner_scope: str, book_id: int, from_chapter: int | None):
        start = max(0, int(from_chapter if from_chapter is not None else 0))
        try:
            return await self.repo.get_chapters_by_book(
                owner_scope,
                book_id,
                start_num=start,
                limit=100000,
            )
        except TypeError:
            return await self.repo.get_chapters_by_book(owner_scope, book_id)

    async def _extract(self, chapter):
        method = getattr(self.extractor, "extract_with_evidence", None)
        evidence_method = callable(method)
        if not callable(method):
            method = getattr(self.extractor, "extract_from_chapter", None)
        if not callable(method):
            method = getattr(self.extractor, "extract", None)
        if not callable(method):
            return [], [], None
        args = (chapter.book_id, chapter.canonical_num, chapter.chapter_title, chapter.raw_text or "")
        try:
            if evidence_method:
                output = method(*args, chapter_id=chapter.id)
            else:
                output = method(*args)
        except TypeError:
            output = method(*args) if evidence_method else method(chapter)
        if inspect.isawaitable(output):
            output = await output
        if isinstance(output, dict):
            return output.get("entities", []), output.get("relationships", []), output.get("structured")
        if isinstance(output, tuple) and len(output) == 2:
            return output[0] or [], output[1] or [], None
        if isinstance(output, tuple) and len(output) >= 3:
            return output[0] or [], output[1] or [], output[2]
        return output or [], [], None

    async def _validate_structured(self, payload, chapter):
        validator = self.structured_extractor
        if payload is None or validator is None:
            return None
        parse = getattr(validator, "parse", None)
        if callable(parse):
            return parse(
                payload,
                chapter_id=chapter.id,
                chapter_text=chapter.raw_text or "",
            )
        method = getattr(validator, "extract", None)
        if not callable(method) and callable(validator):
            method = validator
        if not callable(method):
            return None
        output = method(chapter)
        if inspect.isawaitable(output):
            output = await output
        parse = getattr(validator, "parse", None)
        if callable(parse):
            return parse(output, chapter_id=chapter.id, chapter_text=chapter.raw_text or "")
        return output

    async def _rebuild_knowledge(self, owner_scope: str, book_id: int) -> None:
        replace = getattr(self.repo, "replace_book_knowledge", None)
        list_states = getattr(self.repo, "list_index_states", None)
        if not callable(replace) or not callable(list_states):
            return
        states = list_states(owner_scope, int(book_id))
        if inspect.isawaitable(states):
            states = await states
        snapshots = [
            state.extraction_payload
            for state in states or []
            if state.extraction_status == "completed" and state.extraction_payload
        ]
        await replace(owner_scope, int(book_id), snapshots)

    @classmethod
    def _chapter_snapshot(
        cls,
        chapter,
        *,
        entities: list[Any],
        relationships: list[Any],
        events: list[Any],
        state_changes: list[Any],
        structured_status: str,
    ) -> dict[str, Any]:
        return {
            "chapter_id": int(chapter.id),
            "chapter_num": int(chapter.canonical_num),
            "content_hash": chapter.raw_text_hash or cls._hash(chapter.raw_text or ""),
            "algorithm_version": "local-evidence-1",
            "structured_status": structured_status,
            "entities": [cls._record_to_dict(item) for item in entities],
            "relationships": [cls._record_to_dict(item) for item in relationships],
            "events": [cls._record_to_dict(item) for item in events],
            "state_changes": [cls._record_to_dict(item) for item in state_changes],
        }

    @classmethod
    def _record_to_dict(cls, record: Any) -> dict[str, Any]:
        if isinstance(record, dict):
            data = dict(record)
        elif hasattr(record, "model_dump"):
            data = record.model_dump()
        elif hasattr(record, "dict") and callable(record.dict):
            data = record.dict()
        else:
            try:
                data = dict(vars(record))
            except TypeError:
                return {}
        return cls._json_safe(data)

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._json_safe(item) for item in value]
        if hasattr(value, "model_dump"):
            return cls._json_safe(value.model_dump())
        return value

    async def _persist_local_results(
        self,
        owner_scope: str,
        entities: list[NovelEntity],
        relationships: list[NovelRelationship],
        structured=None,
        *,
        book_id: int,
        chapter_num: int | None = None,
    ) -> None:
        merged_entities = self.extractor.merge_entities(entities) if hasattr(self.extractor, "merge_entities") else entities
        for entity in merged_entities:
            await self.repo.save_entity(owner_scope, entity)

        structured_relationships, structured_events, structured_states = self._structured_entities(
            structured,
            book_id,
            chapter_num=chapter_num,
        )
        relationships = list(relationships or []) + structured_relationships
        seen = await self._relationship_seen(owner_scope, relationships)
        for relationship in relationships:
            key = self._relationship_key(relationship)
            if key in seen:
                continue
            seen.add(key)
            await self.repo.save_relationship(owner_scope, relationship)

        events_seen = await self._event_seen(owner_scope, structured_events)
        for event in structured_events:
            key = self._event_key(event)
            if key in events_seen:
                continue
            events_seen.add(key)
            await self.repo.save_event(owner_scope, event)

        states_seen = await self._state_seen(owner_scope, structured_states)
        for state in structured_states:
            key = self._state_key(state)
            if key in states_seen:
                continue
            states_seen.add(key)
            await self.repo.save_state_change(owner_scope, state)

    async def _relationship_seen(self, owner_scope: str, relationships) -> set[tuple]:
        key = (owner_scope, int(relationships[0].book_id)) if relationships else None
        if key is None:
            return set()
        if key not in self._relationship_keys:
            existing = await self._repo_list("get_relationships", owner_scope, key[1], limit=100000)
            self._relationship_keys[key] = {self._relationship_key(item) for item in existing or []}
        return self._relationship_keys[key]

    async def _event_seen(self, owner_scope: str, events) -> set[tuple]:
        key = (owner_scope, int(events[0].book_id)) if events else None
        if key is None:
            return set()
        if key not in self._event_keys:
            existing = await self._repo_list("get_events", owner_scope, key[1], limit=100000)
            self._event_keys[key] = {self._event_key(item) for item in existing or []}
        return self._event_keys[key]

    async def _state_seen(self, owner_scope: str, states) -> set[tuple]:
        key = (owner_scope, int(states[0].book_id)) if states else None
        if key is None:
            return set()
        if key not in self._state_keys:
            existing = await self._repo_list("get_state_changes", owner_scope, key[1], limit=100000)
            self._state_keys[key] = {self._state_key(item) for item in existing or []}
        return self._state_keys[key]

    async def _repo_list(self, name: str, owner_scope: str, book_id: int, **kwargs):
        method = getattr(self.repo, name, None)
        if not callable(method):
            return []
        try:
            value = method(owner_scope, book_id, **kwargs)
        except TypeError:
            value = method(book_id, **kwargs)
        if inspect.isawaitable(value):
            value = await value
        return value

    @staticmethod
    def _structured_entities(structured, book_id: int, *, chapter_num: int | None = None):
        if structured is None:
            return [], [], []
        relationships = [
            NovelRelationship(
                book_id=book_id,
                source_entity=item.source_entity,
                target_entity=item.target_entity,
                relation_type=item.relation_type if isinstance(item.relation_type, RelationType) else RelationType(item.relation_type),
                description=item.description,
                since_chapter=(
                    chapter_num
                    if chapter_num is not None
                    else (item.evidence[0].chapter_id if item.evidence else 0)
                ),
                confidence=item.confidence,
                evidence=[NovelIndexService._record_to_dict(evidence) for evidence in item.evidence],
            )
            for item in getattr(structured, "relationships", [])
        ]
        events = [
            NovelEvent(
                book_id=book_id,
                chapter_id=item.chapter_id,
                chapter_num=chapter_num if chapter_num is not None else item.chapter_id,
                event_type=item.event_type if isinstance(item.event_type, EventType) else EventType(item.event_type),
                description=item.description,
                participants=list(item.participants),
                location=item.location,
                importance=item.importance,
                related_entities=list(item.participants),
                evidence=[NovelIndexService._record_to_dict(evidence) for evidence in item.evidence],
            )
            for item in getattr(structured, "events", [])
        ]
        states = [
            NovelStateChange(
                book_id=book_id,
                entity_name=item.entity_name,
                chapter_id=item.chapter_id,
                chapter_num=chapter_num if chapter_num is not None else item.chapter_id,
                field_name=item.field_name if isinstance(item.field_name, StateField) else StateField(item.field_name),
                before_value=item.before_value,
                after_value=item.after_value,
                trigger_event=item.trigger_event,
                confidence=item.confidence,
                evidence=[NovelIndexService._record_to_dict(evidence) for evidence in item.evidence],
            )
            for item in getattr(structured, "state_changes", [])
        ]
        return relationships, events, states

    async def _index_vector(self, owner_scope: str, chapter, state: NovelIndexState) -> None:
        if self.vector_store is None or self.embedding is None:
            state.vector_status = "disabled"
            return
        try:
            health = await self.vector_store.health()
        except Exception:
            state.vector_status = "failed"
            return
        if not health.get("enabled"):
            state.vector_status = "disabled"
            return
        try:
            embedding = await self.embedding.embed(chapter.raw_text or "")
        except Exception:
            state.vector_status = "failed"
            return
        if not getattr(embedding, "semantic", False):
            state.vector_status = "disabled"
            return
        state.embedding_model = embedding.model or state.embedding_model
        state.embedding_dimension = embedding.dimension
        self.embedding_model = state.embedding_model
        self.embedding_dimension = state.embedding_dimension
        try:
            await self.vector_store.upsert(
                [
                    VectorRecord(
                        owner_scope=owner_scope,
                        book_id=chapter.book_id,
                        chapter_id=chapter.id,
                        knowledge_version=self.knowledge_version,
                        vector=embedding.vector,
                        payload={
                            "chapter_num": chapter.canonical_num,
                            "chapter_id": chapter.id,
                            "title": chapter.chapter_title,
                            "text": (chapter.raw_text or "")[:2000],
                        },
                    )
                ]
            )
        except Exception:
            state.vector_status = "failed"
            return
        state.vector_status = "completed"

    def _can_skip(self, state: NovelIndexState | None, content_hash: str) -> bool:
        return bool(
            state
            and state.content_hash == content_hash
            and state.knowledge_version == self.knowledge_version
            and state.extraction_status == "completed"
            and state.embedding_model == self.embedding_model
            and state.embedding_dimension == self.embedding_dimension
        )

    @staticmethod
    def _relationship_key(relationship: NovelRelationship) -> tuple:
        return (
            relationship.book_id,
            relationship.source_entity.strip().casefold(),
            relationship.target_entity.strip().casefold(),
            getattr(relationship.relation_type, "value", relationship.relation_type),
            relationship.since_chapter,
            " ".join(relationship.description.split()).casefold(),
        )

    @staticmethod
    def _event_key(event: NovelEvent) -> tuple:
        return (
            event.book_id,
            event.chapter_id,
            tuple(sorted(name.strip().casefold() for name in event.participants)),
            " ".join(event.description.split()).casefold(),
        )

    @staticmethod
    def _state_key(state: NovelStateChange) -> tuple:
        return (
            state.book_id,
            state.entity_name.strip().casefold(),
            state.chapter_id,
            getattr(state.field_name, "value", state.field_name),
            state.before_value.strip(),
            state.after_value.strip(),
        )

    @staticmethod
    def _chapter_index_text(chapter) -> str:
        return " ".join(
            part
            for part in (
                chapter.chapter_title or "",
                chapter.summary or "",
                " ".join(chapter.key_events or []),
                chapter.raw_text or "",
            )
            if part
        )

    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
