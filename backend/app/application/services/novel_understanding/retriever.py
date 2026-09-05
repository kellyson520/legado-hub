"""Owner-scoped BM25, vector and knowledge-graph retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.domain.entities.novel import NovelBook
from app.domain.repositories.vector_store import VectorStore

from .bm25_index import BM25Index
from .embedding import EmbeddingAdapter, EmbeddingUnavailable


@dataclass
class RetrievalResult:
    source: str
    item_type: str
    item_id: int
    score: float
    content: str
    owner_scope: str = "legacy"
    book_id: int = 0
    chapter_num: int = 0
    evidence: str = ""
    confidence: float = 0.0
    book_title: str = ""
    record_key: str = ""
    citation: dict[str, Any] = field(default_factory=dict)
    knowledge_version: str = ""


class RAGRetriever:
    """Three-track retrieval with explicit owner/book/version boundaries."""

    WEIGHT_BM25 = 0.4
    WEIGHT_VECTOR = 0.3
    WEIGHT_KG = 0.3

    def __init__(
        self,
        repo,
        bm25_index: Optional[BM25Index] = None,
        embedding: Optional[EmbeddingAdapter] = None,
        vector_store: VectorStore | None = None,
        similarity_threshold: float = 0.0,
    ):
        self._repo = repo
        self._bm25 = bm25_index or BM25Index()
        self._embedding = embedding or EmbeddingAdapter()
        self._vector_store = vector_store
        self._similarity_threshold = max(0.0, min(1.0, float(similarity_threshold)))
        self._indexes: dict[tuple[str, int, str], BM25Index] = {}
        self._chapter_cache: dict[tuple[str, int, str], dict[int, Any]] = {}

    async def retrieve(
        self,
        owner_scope: str | int | None = None,
        book_id: int | str | None = None,
        query: str | None = None,
        top_k: int = 10,
        knowledge_version: str = "",
    ) -> List[RetrievalResult]:
        owner_scope, book_id, query = self._normalize_retrieve_args(owner_scope, book_id, query)
        key = (owner_scope, int(book_id), knowledge_version)
        index = self._indexes.get(key)
        if index is None or not index.documents:
            await self.build_bm25_index(owner_scope, int(book_id), knowledge_version=knowledge_version)
            index = self._indexes.get(key, self._bm25)

        results: Dict[str, RetrievalResult] = {}
        tracks: dict[str, list[RetrievalResult]] = {
            "bm25": [],
            "kg": [],
            "vector": [],
        }
        chapter_cache = self._chapter_cache.get(key, {})
        matched_chapters = index.search(query, top_k=max(1, top_k * 2)) if query else []
        if not query:
            matched_chapters = [
                (chapter_id, 0.01)
                for chapter_id in list(chapter_cache)[: max(1, top_k * 2)]
            ]
        for doc_id, score in matched_chapters:
            tracks["bm25"].append(
                RetrievalResult(
                    source="bm25",
                    item_type="chapter",
                    item_id=int(doc_id),
                    score=float(score),
                    content="",
                    owner_scope=owner_scope,
                    book_id=int(book_id),
                    confidence=min(1.0, float(score)),
                )
            )

        if query:
            tracks["kg"].extend(await self._retrieve_kg(owner_scope, int(book_id), query, top_k=top_k))

        if self._vector_store is not None and query:
            try:
                embedding = await self._embedding.embed(query)
                if getattr(embedding, "semantic", False):
                    vector_results = await self._vector_store.search(
                        owner_scope,
                        int(book_id),
                        knowledge_version,
                        embedding.vector,
                        top_k=max(1, top_k * 2),
                    )
                    for item in vector_results:
                        if float(item.score) < self._similarity_threshold:
                            continue
                        payload = item.payload or {}
                        chapter_id = int(payload.get("chapter_id", item.chapter_id))
                        memory_type = str(payload.get("memory_type") or "chapter")
                        record_key = item.record_key or str(
                            payload.get("record_key") or f"chapter:{chapter_id}"
                        )
                        item_id = int(payload.get("item_id", payload.get("entity_id", chapter_id)) or chapter_id)
                        content = str(
                            payload.get("text") or payload.get("card") or payload.get("content") or ""
                        )[:2000]
                        evidence = _evidence_text(payload.get("evidence"), content)
                        tracks["vector"].append(
                            RetrievalResult(
                                source="vector",
                                item_type=memory_type,
                                item_id=item_id,
                                score=float(item.score),
                                content=content,
                                owner_scope=owner_scope,
                                book_id=int(book_id),
                                chapter_num=int(payload.get("chapter_num", 0) or 0),
                                evidence=evidence,
                                confidence=max(0.0, min(1.0, float(item.score))),
                                record_key=record_key,
                                citation=dict(
                                    payload.get("citation")
                                    or {"chapter_id": chapter_id, "chapter_num": int(payload.get("chapter_num", 0) or 0)}
                                ),
                                knowledge_version=knowledge_version,
                            )
                        )
            except (EmbeddingUnavailable, RuntimeError, ValueError):
                # BM25 and structured knowledge remain useful when semantic
                # embeddings or the external vector backend are unavailable.
                pass

        track_weights = {
            "bm25": self.WEIGHT_BM25,
            "vector": self.WEIGHT_VECTOR,
            "kg": self.WEIGHT_KG,
        }
        for source, items in tracks.items():
            for item in self._normalize_scores(items):
                self._merge_result(results, item, weight=track_weights[source])

        sorted_results = sorted(results.values(), key=lambda item: item.score, reverse=True)
        book = await self._repo_call("get_book_by_id", owner_scope, int(book_id), legacy=(int(book_id),))
        book_title = book.book_name if book else ""
        for result in sorted_results[: max(0, int(top_k))]:
            result.book_title = book_title
            if result.item_type == "chapter":
                chapter = chapter_cache.get(result.item_id)
                if chapter is None:
                    chapter = await self._repo_call(
                        "get_chapter_by_id",
                        owner_scope,
                        result.item_id,
                        legacy=(result.item_id,),
                    )
                if chapter:
                    result.book_id = chapter.book_id
                    result.chapter_num = chapter.canonical_num
                    preview = (chapter.raw_text or "")[:200] or chapter.summary or chapter.chapter_title
                    result.content = result.content or f"第{chapter.canonical_num}章 {chapter.chapter_title}\n{preview}"
                    result.evidence = result.evidence or preview[:500]
                    result.confidence = result.confidence or 0.5
            result.evidence = (result.evidence or result.content)[:500]
            result.confidence = max(0.0, min(1.0, result.confidence or min(1.0, result.score)))
        return sorted_results[: max(0, int(top_k))]

    async def _retrieve_kg(
        self,
        owner_scope: str,
        book_id: int,
        query: str,
        top_k: int,
    ) -> List[RetrievalResult]:
        kg_results: list[RetrievalResult] = []
        entities = await self._repo_call(
            "search_entities",
            owner_scope,
            book_id,
            query,
            limit=top_k,
            legacy=(book_id, query),
        )
        entity_method = getattr(self._repo, "list_entities", None)
        if not entities and callable(entity_method):
            entities = await self._repo_call(
                "list_entities",
                owner_scope,
                book_id,
                limit=max(top_k * 4, 20),
                legacy=(book_id,),
            )
        query_tokens = self._query_terms(query)
        for entity in entities or []:
            score = self._match_score(
                query_tokens,
                " ".join(
                    [
                        str(getattr(entity, "name", "")),
                        " ".join(getattr(entity, "aliases", []) or []),
                        str(getattr(entity, "description", "")),
                    ]
                ),
            )
            if score <= 0:
                continue
            content = f"{entity.name}({getattr(entity.entity_type, 'value', entity.entity_type)}): {entity.description}"
            kg_results.append(
                RetrievalResult(
                    source="kg",
                    item_type="entity",
                    item_id=entity.id,
                    score=score,
                    content=content,
                    owner_scope=owner_scope,
                    book_id=book_id,
                    chapter_num=entity.first_appearance_ch,
                    evidence=content,
                    confidence=score,
                )
            )

        events = await self._repo_call(
            "get_events",
            owner_scope,
            book_id,
            limit=top_k * 2,
            legacy=(book_id,),
        )
        for event in events or []:
            score = self._match_score(
                query_tokens,
                " ".join(
                    [
                        str(getattr(event, "description", "")),
                        " ".join(getattr(event, "participants", []) or []),
                        str(getattr(event, "event_type", "")),
                    ]
                ),
            )
            if score > 0:
                content = f"第{event.chapter_num}章事件: {event.description}"
                kg_results.append(
                    RetrievalResult(
                        source="kg",
                        item_type="event",
                        item_id=event.id,
                        score=score,
                        content=content,
                        owner_scope=owner_scope,
                        book_id=book_id,
                        chapter_num=event.chapter_num,
                        evidence=content,
                        confidence=score,
                    )
                )

        relationships = await self._repo_call(
            "get_relationships",
            owner_scope,
            book_id,
            limit=top_k,
            legacy=(book_id,),
        )
        for relationship in relationships or []:
            relation_type = getattr(relationship.relation_type, "value", relationship.relation_type)
            relation_terms = self._RELATION_TERMS.get(str(relation_type).lower(), ())
            relationship_tokens = self._query_terms(
                " ".join(
                    [
                        relationship.source_entity,
                        relationship.target_entity,
                        relationship.description,
                        str(relation_type),
                        " ".join(relation_terms),
                    ]
                )
            )
            score = self._overlap_score(query_tokens, relationship_tokens)
            if score > 0:
                content = (
                    f"{relationship.source_entity} -"
                    f"{getattr(relationship.relation_type, 'value', relationship.relation_type)}-> "
                    f"{relationship.target_entity}: {relationship.description}"
                )
                kg_results.append(
                    RetrievalResult(
                        source="kg",
                        item_type="relationship",
                        item_id=relationship.id,
                        score=score,
                        content=content,
                        owner_scope=owner_scope,
                        book_id=book_id,
                        chapter_num=relationship.since_chapter,
                        evidence=content,
                        confidence=0.6,
                    )
                )
        return sorted(kg_results, key=lambda item: item.score, reverse=True)[:top_k]

    async def build_bm25_index(
        self,
        owner_scope: str | int | None = None,
        book_id: int | None = None,
        knowledge_version: str = "",
    ):
        if book_id is None:
            book_id = int(owner_scope)
            owner_scope = "legacy"
        owner_scope = str(owner_scope or "legacy")
        key = (owner_scope, int(book_id), knowledge_version)
        index = self._bm25 if len(self._indexes) == 0 and self._bm25 is not None else BM25Index()
        index.clear()
        chapters = await self._repo_call(
            "get_chapters_by_book",
            owner_scope,
            int(book_id),
            limit=100000,
            legacy=(int(book_id),),
        )
        cache: dict[int, Any] = {}
        for chapter in chapters or []:
            index.add_document(chapter.id, self._chapter_index_text(chapter))
            cache[chapter.id] = chapter
        index.build()
        self._indexes[key] = index
        self._chapter_cache[key] = cache
        self._chapter_cache = {**self._chapter_cache, key: cache}
        return index

    async def get_character_context(
        self,
        owner_scope: str | int,
        character_name: str,
        book_id: int | None = None,
    ) -> str:
        if book_id is None:
            book_id, owner_scope = int(owner_scope), "legacy"
        parts = []
        entity = await self._repo_call(
            "get_entity_by_name",
            owner_scope,
            book_id,
            character_name,
            legacy=(book_id, character_name),
        )
        if entity:
            parts.extend(
                [
                    f"【角色档案】{entity.name}",
                    f"类型: {getattr(entity.entity_type, 'value', entity.entity_type)}",
                    f"描述: {entity.description}",
                ]
            )
            if entity.aliases:
                parts.append(f"别名: {', '.join(entity.aliases)}")
            parts.append(f"重要性: {entity.importance_score}/5")
        relationships = await self._repo_call(
            "get_relationships",
            owner_scope,
            book_id,
            entity_name=character_name,
            legacy=(book_id,),
        )
        if relationships:
            parts.append("【人际关系】")
            parts.extend(
                f"  {item.source_entity} -{getattr(item.relation_type, 'value', item.relation_type)}-> "
                f"{item.target_entity}: {item.description}"
                for item in relationships
            )
        state_changes = await self._repo_call(
            "get_state_changes",
            owner_scope,
            book_id,
            entity_name=character_name,
            legacy=(book_id,),
        )
        if state_changes:
            parts.append("【状态变迁】")
            parts.extend(
                f"  第{item.chapter_num}章: {getattr(item.field_name, 'value', item.field_name)} "
                f"[{item.before_value}] -> [{item.after_value}]"
                for item in sorted(state_changes, key=lambda value: value.chapter_num)
            )
        events = await self._repo_call("get_events", owner_scope, book_id, limit=50, legacy=(book_id,))
        character_events = [
            item
            for item in events or []
            if character_name in item.participants or character_name in item.related_entities
        ]
        if character_events:
            parts.append("【参与事件】")
            parts.extend(f"  第{item.chapter_num}章: {item.description}" for item in character_events[:10])
        return "\n".join(parts)

    async def get_world_context(self, owner_scope: str | int, book_id: int | None = None) -> str:
        if book_id is None:
            book_id, owner_scope = int(owner_scope), "legacy"
        parts = ["【世界观设定】"]
        entities = await self._repo_call("list_entities", owner_scope, book_id, limit=100, legacy=(book_id,))
        for entity_type, title in (("location", "【地点】"), ("faction", "【势力】"), ("realm", "【境界体系】"), ("concept", "【核心概念】")):
            selected = [item for item in entities or [] if getattr(item.entity_type, "value", item.entity_type) == entity_type]
            if selected:
                parts.append(title)
                parts.extend(f"  {item.name}: {item.description}" for item in selected[:15])
        return "\n".join(parts)

    async def get_storyline_context(self, owner_scope: str | int, book_id: int | None = None) -> str:
        if book_id is None:
            book_id, owner_scope = int(owner_scope), "legacy"
        parts = ["【剧情时间线】"]
        events = await self._repo_call("get_events", owner_scope, book_id, min_importance=3, limit=50, legacy=(book_id,))
        for event in sorted(events or [], key=lambda value: value.chapter_num):
            parts.append(f"第{event.chapter_num}章 [{getattr(event.event_type, 'value', event.event_type)}] {event.description}")
            if event.participants:
                parts.append(f"  参与者: {', '.join(event.participants)}")
        return "\n".join(parts)

    async def _repo_call(self, name: str, *args, legacy=(), **kwargs):
        method = getattr(self._repo, name)
        try:
            result = method(*args, **kwargs)
        except TypeError:
            result = method(*legacy)
        if hasattr(result, "__await__"):
            return await result
        return result

    @staticmethod
    def _normalize_retrieve_args(owner_scope, book_id, query):
        if owner_scope is None:
            return "legacy", int(book_id), str(query or "").strip()
        if query is None and isinstance(owner_scope, int) and isinstance(book_id, str):
            return "legacy", int(owner_scope), book_id.strip()
        return str(owner_scope), int(book_id), str(query or "").strip()

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

    _RELATION_TERMS = {
        "master": ("师父", "师傅", "授业", "弟子", "拜师", "master"),
        "subordinate": ("徒弟", "弟子", "下属", "subordinate"),
        "ally": ("同伴", "盟友", "朋友", "ally"),
        "enemy": ("敌人", "仇敌", "enemy"),
        "lover": ("恋人", "情侣", "夫妻", "lover"),
        "family": ("家人", "亲属", "父母", "family"),
        "rival": ("对手", "宿敌", "rival"),
    }

    @staticmethod
    def _query_terms(value: str) -> set[str]:
        tokens = set(BM25Index._tokenize(str(value or "")))
        normalized = str(value or "").strip().casefold()
        if normalized:
            tokens.add(normalized)
        return {token.casefold() for token in tokens if token}

    @classmethod
    def _match_score(cls, query_tokens: set[str], value: str) -> float:
        return cls._overlap_score(query_tokens, cls._query_terms(value))

    @staticmethod
    def _overlap_score(query_tokens: set[str], value_tokens: set[str]) -> float:
        if not query_tokens or not value_tokens:
            return 0.0
        overlap = sum(1 for token in query_tokens if any(token in candidate or candidate in token for candidate in value_tokens))
        return min(1.0, overlap / max(1, len(query_tokens)))

    @staticmethod
    def _normalize_scores(items: list[RetrievalResult]) -> list[RetrievalResult]:
        """Normalize one retrieval track before applying its configured weight."""
        if not items:
            return items
        values = [float(item.score) for item in items]
        low, high = min(values), max(values)
        if high == low:
            normalized = 1.0 if high > 0 else 0.0
            for item in items:
                item.score = normalized
            return items
        scale = high - low
        for item in items:
            item.score = max(0.0, min(1.0, (float(item.score) - low) / scale))
        return items

    @staticmethod
    def _merge_result(results: dict[str, RetrievalResult], result: RetrievalResult, weight: float = 1.0) -> None:
        key = f"{result.item_type}:{result.record_key or result.item_id}"
        result.score *= weight
        existing = results.get(key)
        if existing is None:
            results[key] = result
            return
        existing.score += result.score
        existing.evidence = existing.evidence or result.evidence
        existing.content = existing.content or result.content
        existing.chapter_num = existing.chapter_num or result.chapter_num
        existing.confidence = max(existing.confidence, result.confidence)
        existing.record_key = existing.record_key or result.record_key
        existing.citation = existing.citation or result.citation
        existing.knowledge_version = existing.knowledge_version or result.knowledge_version


def _evidence_text(value: Any, fallback: str) -> str:
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value[:3]:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("excerpt") or ""))
            else:
                parts.append(str(item))
        text = "；".join(part for part in parts if part.strip())
        if text:
            return text[:500]
    if isinstance(value, dict):
        return str(value.get("text") or value.get("excerpt") or fallback)[:500]
    return str(value or fallback)[:500]
