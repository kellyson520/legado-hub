"""Incremental chapter understanding and index checkpoint orchestration."""

from __future__ import annotations

import hashlib
import inspect
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import SimpleNamespace
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
from .memory_cards import entity_memory_card, event_memory_card, memory_card_hash, state_memory_card


@dataclass
class IndexResult:
    owner_scope: str
    book_id: int
    processed_chapters: int = 0
    skipped_chapters: int = 0
    failed_chapters: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    indexed_chapters: list[int] = field(default_factory=list)
    status: str = "pending"
    no_chapters: bool = False
    timings_ms: dict[str, int] = field(default_factory=dict)

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
        adjudicator=None,
        adaptive_learning=None,
        learning_service=None,
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
        self._owns_extractor = extractor is None
        self.extractor = extractor or AutoExtractor()
        self.structured_extractor = structured_extractor
        self.adjudicator = adjudicator
        self.adaptive_learning = adaptive_learning or learning_service
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
        started_at = time.perf_counter()
        result = IndexResult(owner_scope=owner_scope, book_id=int(book_id))
        stage_started = time.perf_counter()
        learning_profile = await self._load_learning_profile(owner_scope, book_id)
        learning_profile_version = str(learning_profile.get("profile_version") or "")
        result.timings_ms["learning_profile"] = _elapsed_ms(stage_started)
        stage_started = time.perf_counter()
        chapters = await self._chapters(owner_scope, book_id, from_chapter)
        result.timings_ms["chapters"] = _elapsed_ms(stage_started)
        if not chapters:
            stage_started = time.perf_counter()
            await self._rebuild_knowledge(owner_scope, book_id)
            result.timings_ms["rebuild_knowledge"] = _elapsed_ms(stage_started)
            result.no_chapters = True
            result.status = "no_chapters"
            result.timings_ms["total"] = _elapsed_ms(started_at)
            return result

        stage_started = time.perf_counter()
        bm25 = self.bm25_index or self._bm25_indexes.setdefault(
            (owner_scope, int(book_id), self.knowledge_version), BM25Index()
        )
        bm25.clear()
        for chapter in chapters:
            bm25.add_document(chapter.id, self._chapter_index_text(chapter))
        bm25.build()
        result.timings_ms["bm25"] = _elapsed_ms(stage_started)

        pending_vectors: list[tuple[Any, NovelIndexState, dict[str, Any]]] = []
        for chapter in chapters:
            content = chapter.raw_text or ""
            content_hash = chapter.raw_text_hash or self._hash(content)
            state = await self.repo.get_index_state(owner_scope, book_id, chapter.id)
            if self._can_skip(state, content_hash, learning_profile_version):
                result.skipped_chapters += 1
                continue

            previous_payload = dict(getattr(state, "extraction_payload", {}) or {}) if state else {}
            previous_success_at = getattr(state, "last_success_at", None) if state else None
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
                extraction_payload=previous_payload,
                last_success_at=previous_success_at,
            )
            await self.repo.save_index_state(state)
            try:
                entities, relationships, structured = await self._extract(chapter)
                entities = await self._adjudicate_entities(
                    owner_scope,
                    chapter.book_id,
                    entities,
                    content_hash=content_hash,
                )
                structured_status = "not_requested"
                try:
                    if structured is not None and self.structured_extractor is not None:
                        structured_status = "completed"
                        structured = await self._validate_structured(structured, chapter)
                    elif structured is None:
                        structured_status = "not_requested"
                except Exception as exc:
                    # A structured failure invalidates the chapter snapshot.
                    # Keep the previous checkpoint materialized and retry the
                    # chapter later instead of replacing the book projection
                    # with incomplete facts.
                    structured = None
                    structured_status = "failed"
                    state.extraction_payload = self._chapter_snapshot(
                        chapter,
                        entities=list(entities or []),
                        relationships=list(relationships or []),
                        events=[],
                        state_changes=[],
                        structured_status=structured_status,
                        learning_profile_version=learning_profile_version,
                    )
                    state.failure_reason = f"structured extraction: {str(exc)[:450]}"
                    state.extraction_status = "failed"
                    await self.repo.save_index_state(state)
                    result.failed_chapters += 1
                    result.errors.append({"chapter_id": chapter.id, "error": str(exc)[:500], "scope": "structured"})
                    continue

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
                    learning_profile_version=learning_profile_version,
                )
                state.extraction_payload = snapshot
                state.extraction_status = "completed"
                state.bm25_status = "completed"
                state.last_success_at = datetime.now(timezone.utc)
                if structured_status != "failed":
                    state.failure_reason = ""
                pending_vectors.append((chapter, state, snapshot))
                result.processed_chapters += 1
                result.indexed_chapters.append(int(chapter.id))
            except Exception as exc:
                state.extraction_status = "failed"
                state.failure_reason = str(exc)[:500]
                await self.repo.save_index_state(state)
                result.failed_chapters += 1
                result.errors.append({"chapter_id": chapter.id, "error": str(exc)[:500]})
        stage_started = time.perf_counter()
        await self._index_vectors(owner_scope, pending_vectors)
        result.timings_ms["vectors"] = _elapsed_ms(stage_started)
        stage_started = time.perf_counter()
        await self._rebuild_knowledge(owner_scope, book_id)
        result.timings_ms["rebuild_knowledge"] = _elapsed_ms(stage_started)
        if result.failed_chapters:
            result.status = "partial" if result.processed_chapters or result.skipped_chapters else "failed"
        else:
            result.status = "completed"
        result.timings_ms["total"] = _elapsed_ms(started_at)
        return result

    async def _load_learning_profile(self, owner_scope: str, book_id: int) -> dict[str, Any]:
        profile: dict[str, Any] = {}
        service = self.adaptive_learning
        getter = getattr(service, "get_profile", None) if service is not None else None
        if callable(getter):
            try:
                value = getter(owner_scope, int(book_id))
                if inspect.isawaitable(value):
                    value = await value
                if isinstance(value, dict):
                    profile = dict(value)
            except Exception:
                profile = {}

        setter = getattr(self.extractor, "set_learning_profile", None)
        if callable(setter):
            setter(profile)
        elif self._owns_extractor and profile:
            self.extractor = AutoExtractor(profile)
        return profile

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

    async def _adjudicate_entities(
        self,
        owner_scope: str,
        book_id: int,
        entities: list[Any],
        *,
        content_hash: str = "",
    ) -> list[Any]:
        if self.adjudicator is None:
            return list(entities or [])
        candidates = []
        for entity in entities or []:
            attributes = dict(getattr(entity, "attributes", {}) or {})
            status = str(attributes.get("extraction_status") or "confirmed")
            if status not in {"candidate", "conflict"}:
                continue
            candidates.append(
                {
                    "name": entity.name,
                    "entity_type": getattr(entity.entity_type, "value", entity.entity_type),
                    "score": float(attributes.get("confidence", 0.0) or 0.0),
                    "mentions": int(attributes.get("mention_count", entity.appearance_count) or 0),
                    "aliases": list(entity.aliases or []),
                    "subtype": str(attributes.get("subtype") or ""),
                    "status": status,
                    "evidence": list(attributes.get("evidence") or []),
                    "content_hash": str(attributes.get("content_hash") or content_hash or ""),
                }
            )
        if not candidates:
            return list(entities or [])
        try:
            decisions = self.adjudicator.adjudicate(owner_scope, int(book_id), candidates)
            if inspect.isawaitable(decisions):
                decisions = await decisions
        except Exception:
            return list(entities or [])
        by_name = {
            str(item.get("name") or "").strip(): item
            for item in decisions or []
            if isinstance(item, dict) and item.get("name")
        }
        await self._learn_adjudication(owner_scope, int(book_id), candidates, by_name)
        accepted = []
        for entity in entities or []:
            decision = by_name.get(entity.name)
            if decision is None:
                accepted.append(entity)
                continue
            attributes = dict(getattr(entity, "attributes", {}) or {})
            verdict = str(decision.get("verdict") or "pending")
            attributes["adjudication"] = {
                "verdict": verdict,
                "source": decision.get("source", "agent"),
                "reason": decision.get("reason", ""),
                "evidence_ids": list(decision.get("evidence_ids") or []),
            }
            if verdict == "reject":
                continue
            attributes["extraction_status"] = "confirmed" if verdict in {"accept", "merge", "split"} else "pending"
            entity.attributes = attributes
            accepted.append(entity)
        return accepted

    async def _learn_adjudication(
        self,
        owner_scope: str,
        book_id: int,
        candidates: list[dict[str, Any]],
        decisions: dict[str, dict[str, Any]],
    ) -> None:
        learner = self.adaptive_learning
        method = getattr(learner, "learn_from_adjudication", None) if learner is not None else None
        if not callable(method):
            return
        for candidate in candidates:
            decision = decisions.get(str(candidate.get("name") or "").strip())
            if not isinstance(decision, dict) or str(decision.get("verdict") or "pending") not in {"accept", "reject", "merge"}:
                continue
            try:
                result = method(owner_scope, int(book_id), candidate, decision)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                # Learning is a recovery/optimization side effect.  A failed
                # rule update must not discard the chapter snapshot.
                continue

    async def _rebuild_knowledge(self, owner_scope: str, book_id: int) -> None:
        replace = getattr(self.repo, "replace_book_knowledge", None)
        list_states = getattr(self.repo, "list_index_states", None)
        if not callable(replace) or not callable(list_states):
            return
        states = list_states(owner_scope, int(book_id))
        if inspect.isawaitable(states):
            states = await states
        chapters = await self._chapters(owner_scope, int(book_id), None)
        chapters_by_id = {
            int(getattr(chapter, "id", 0) or 0): chapter
            for chapter in chapters or []
            if int(getattr(chapter, "id", 0) or 0)
        }
        if any(
            state.extraction_status != "completed"
            and isinstance(getattr(state, "extraction_payload", None), dict)
            and state.extraction_payload
            for state in states or []
        ):
            # Keep the last successful materialized projection while a
            # changed chapter is being retried.  Replaying that payload would
            # make old facts look current and deleting it would lose the last
            # usable result.
            return
        snapshots = []
        for state in states or []:
            if state.extraction_status != "completed":
                continue
            if str(getattr(state, "knowledge_version", "") or "") != self.knowledge_version:
                continue
            payload = state.extraction_payload
            if not isinstance(payload, dict):
                continue
            chapter_id = int(getattr(state, "chapter_id", 0) or payload.get("chapter_id", 0) or 0)
            chapter = chapters_by_id.get(chapter_id)
            if chapter is None:
                continue
            state_hash = str(getattr(state, "content_hash", "") or "")
            payload_hash = str(payload.get("content_hash") or "")
            current_hash = str(getattr(chapter, "raw_text_hash", "") or "") or self._hash(
                str(getattr(chapter, "raw_text", "") or "")
            )
            if not state_hash or state_hash != payload_hash or state_hash != current_hash:
                continue
            snapshots.append(payload)
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
        learning_profile_version: str = "",
    ) -> dict[str, Any]:
        chapter_id = int(getattr(chapter, "id", 0) or 0)
        chapter_num = int(getattr(chapter, "canonical_num", 0) or 0)
        raw_text = str(getattr(chapter, "raw_text", "") or "")
        content_hash = str(getattr(chapter, "raw_text_hash", "") or "") or cls._hash(raw_text)
        return {
            "chapter_id": chapter_id,
            "chapter_num": chapter_num,
            "content_hash": content_hash,
            "algorithm_version": "local-evidence-1",
            "learning_profile_version": learning_profile_version,
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

    async def _index_vector(
        self,
        owner_scope: str,
        chapter,
        state: NovelIndexState,
        *,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        await self._index_vectors(owner_scope, [(chapter, state, snapshot or {})])

    async def _index_vectors(
        self,
        owner_scope: str,
        entries: list[tuple[Any, NovelIndexState, dict[str, Any]]],
    ) -> None:
        """Health-check, embed, and upsert all changed chapters as one batch."""
        if not entries:
            return

        states = [state for _, state, _ in entries]

        async def save_states() -> None:
            for state in states:
                await self.repo.save_index_state(state)

        if self.vector_store is None or self.embedding is None:
            for state in states:
                state.vector_status = "disabled"
            await save_states()
            return
        try:
            health = await self.vector_store.health()
        except Exception as exc:
            for state in states:
                state.vector_status = "failed"
                state.failure_reason = f"vector health: {str(exc)[:450]}"
            await save_states()
            return
        if not health.get("enabled"):
            for state in states:
                state.vector_status = "disabled"
            await save_states()
            return

        texts: list[str] = []
        metadata: list[dict[str, Any]] = []
        delete_chapter = getattr(self.vector_store, "delete_chapter", None)
        try:
            for chapter, _, snapshot in entries:
                if callable(delete_chapter):
                    deleted = delete_chapter(
                        owner_scope,
                        int(chapter.book_id),
                        int(chapter.id),
                        self.knowledge_version,
                    )
                    if inspect.isawaitable(deleted):
                        await deleted
                chapter_texts, chapter_metadata = self._vector_payloads(chapter, snapshot)
                texts.extend(chapter_texts)
                metadata.extend(chapter_metadata)
        except Exception as exc:
            for state in states:
                state.vector_status = "failed"
                state.failure_reason = f"vector cleanup: {str(exc)[:450]}"
            await save_states()
            return

        try:
            embed_batch = getattr(self.embedding, "embed_batch", None)
            if callable(embed_batch):
                embeddings = await embed_batch(texts)
            else:
                embeddings = [await self.embedding.embed(text) for text in texts]
        except Exception as exc:
            for state in states:
                state.vector_status = "failed"
                state.failure_reason = f"embedding: {str(exc)[:450]}"
            await save_states()
            return
        if len(embeddings) != len(metadata) or not all(getattr(item, "semantic", False) for item in embeddings):
            for state in states:
                state.vector_status = "disabled"
            await save_states()
            return
        dimension = len(embeddings[0].vector) if embeddings else 0
        if not dimension or any(len(item.vector) != dimension for item in embeddings):
            for state in states:
                state.vector_status = "failed"
                state.failure_reason = "embedding: inconsistent vector dimensions"
            await save_states()
            return
        model = str(getattr(embeddings[0], "model", "") or "")
        for state in states:
            state.embedding_model = model or state.embedding_model
            state.embedding_dimension = dimension
        self.embedding_model = model or self.embedding_model
        self.embedding_dimension = dimension

        chapter_by_id = {
            int(chapter.id): chapter
            for chapter, _, _ in entries
        }
        try:
            await self.vector_store.upsert(
                [
                    VectorRecord(
                        owner_scope=owner_scope,
                        book_id=int(chapter_by_id[int(payload["chapter_id"])].book_id),
                        chapter_id=int(payload["chapter_id"]),
                        knowledge_version=self.knowledge_version,
                        vector=item.vector,
                        payload=payload,
                        record_key=payload["record_key"],
                    )
                    for item, payload in zip(embeddings, metadata)
                ]
            )
        except Exception as exc:
            for state in states:
                state.vector_status = "failed"
                state.failure_reason = f"vector upsert: {str(exc)[:450]}"
            await save_states()
            return
        for state in states:
            state.vector_status = "completed"
        await save_states()

    def _vector_payloads(self, chapter, snapshot: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
        texts = [chapter.raw_text or ""]
        metadata = [
            {
                "memory_type": "chapter",
                "record_key": f"chapter:{int(chapter.id)}",
                "chapter_id": int(chapter.id),
                "chapter_num": int(chapter.canonical_num),
                "title": chapter.chapter_title,
                "text": (chapter.raw_text or "")[:2000],
                "card_hash": memory_card_hash(chapter.raw_text or ""),
            }
        ]
        for raw_entity in snapshot.get("entities") or []:
            entity = SimpleNamespace(**raw_entity)
            card = entity_memory_card(entity)
            texts.append(card)
            name = str(raw_entity.get("name") or "").strip()
            entity_type = str(raw_entity.get("entity_type") or "entity")
            metadata.append(
                {
                    "memory_type": "entity",
                    "record_key": f"entity:{entity_type}:{name.casefold()}",
                    "item_id": _stable_memory_id(f"entity:{entity_type}:{name.casefold()}"),
                    "chapter_id": int(chapter.id),
                    "chapter_num": int(chapter.canonical_num),
                    "name": name,
                    "card": card,
                    "text": card,
                    "evidence": (raw_entity.get("attributes") or {}).get("evidence", []),
                    "card_hash": memory_card_hash(card),
                }
            )
        for raw_event in snapshot.get("events") or []:
            event = SimpleNamespace(**raw_event)
            card = event_memory_card(event)
            texts.append(card)
            event_key = f"event:{int(raw_event.get('chapter_id', chapter.id))}:{memory_card_hash(card)[:16]}"
            metadata.append(
                {
                    "memory_type": "event",
                    "record_key": event_key,
                    "item_id": _stable_memory_id(event_key),
                    "chapter_id": int(raw_event.get("chapter_id", chapter.id)),
                    "chapter_num": int(raw_event.get("chapter_num", chapter.canonical_num)),
                    "card": card,
                    "text": card,
                    "evidence": raw_event.get("evidence", []),
                    "card_hash": memory_card_hash(card),
                }
            )
        for raw_state in snapshot.get("state_changes") or []:
            state_change = SimpleNamespace(**raw_state)
            card = state_memory_card(state_change)
            texts.append(card)
            state_key = f"state:{int(raw_state.get('chapter_id', chapter.id))}:{memory_card_hash(card)[:16]}"
            metadata.append(
                {
                    "memory_type": "state",
                    "record_key": state_key,
                    "item_id": _stable_memory_id(state_key),
                    "chapter_id": int(raw_state.get("chapter_id", chapter.id)),
                    "chapter_num": int(raw_state.get("chapter_num", chapter.canonical_num)),
                    "card": card,
                    "text": card,
                    "evidence": raw_state.get("evidence", []),
                    "card_hash": memory_card_hash(card),
                }
            )
        return texts, metadata

    def _can_skip(self, state: NovelIndexState | None, content_hash: str, learning_profile_version: str = "") -> bool:
        return bool(
            state
            and state.content_hash == content_hash
            and state.knowledge_version == self.knowledge_version
            and state.extraction_status == "completed"
            and (state.extraction_payload or {}).get("learning_profile_version", "") == learning_profile_version
            and (state.extraction_payload or {}).get("structured_status") != "failed"
            and not self._vector_needs_retry(state)
            and state.embedding_model == self.embedding_model
            and state.embedding_dimension == self.embedding_dimension
        )

    def _vector_needs_retry(self, state: NovelIndexState) -> bool:
        if state.vector_status == "failed":
            return True
        if state.vector_status != "disabled":
            return False
        return bool(
            self.vector_store is not None
            and self.embedding is not None
            and getattr(self.vector_store, "retry_disabled", True)
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


def _stable_memory_id(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))
