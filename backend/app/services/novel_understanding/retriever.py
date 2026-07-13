"""
RAG 检索器 - 三轨融合检索

1. BM25 检索（关键词匹配）- 权重 0.4
2. 向量检索（语义相似）- 权重 0.3
3. 知识图谱检索（实体/关系/事件）- 权重 0.3

融合策略：加权分数 + 去重 + 重排序
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.domain.repositories.novel_repo import NovelRepository
from app.domain.entities.novel import NovelEntity, NovelRelationship, NovelEvent, NovelChapter
from .bm25_index import BM25Index
from .embedding import EmbeddingAdapter


@dataclass
class RetrievalResult:
    """检索结果"""
    source: str  # "bm25" / "vector" / "kg"
    item_type: str  # "chapter" / "entity" / "relationship" / "event"
    item_id: int
    score: float
    content: str  # 文本内容


class RAGRetriever:
    """RAG 三轨融合检索器"""

    WEIGHT_BM25 = 0.4
    WEIGHT_VECTOR = 0.3
    WEIGHT_KG = 0.3

    def __init__(
        self,
        repo: NovelRepository,
        bm25_index: Optional[BM25Index] = None,
        embedding: Optional[EmbeddingAdapter] = None,
    ):
        self._repo = repo
        self._bm25 = bm25_index or BM25Index()
        self._embedding = embedding or EmbeddingAdapter()

    async def retrieve(
        self,
        book_id: int,
        query: str,
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        """
        三轨融合检索

        Returns:
            按融合分数排序的检索结果列表
        """
        results: Dict[str, RetrievalResult] = {}

        # 1. BM25 检索
        bm25_results = self._bm25.search(query, top_k=top_k * 2)
        for doc_id, score in bm25_results:
            key = f"chapter:{doc_id}"
            results[key] = RetrievalResult(
                source="bm25",
                item_type="chapter",
                item_id=doc_id,
                score=score * self.WEIGHT_BM25,
                content="",
            )

        # 2. 知识图谱检索
        kg_results = await self._retrieve_kg(book_id, query, top_k=top_k)
        for r in kg_results:
            key = f"{r.item_type}:{r.item_id}"
            if key in results:
                results[key].score += r.score * self.WEIGHT_KG
            else:
                results[key] = RetrievalResult(
                    source="kg",
                    item_type=r.item_type,
                    item_id=r.item_id,
                    score=r.score * self.WEIGHT_KG,
                    content=r.content,
                )

        # 3. 按分数排序
        sorted_results = sorted(results.values(), key=lambda x: x.score, reverse=True)

        # 4. 填充内容
        for r in sorted_results[:top_k]:
            if r.item_type == "chapter":
                ch = getattr(self, '_chapter_cache', {}).get(r.item_id)
                if not ch:
                    ch = await self._repo.get_chapter(r.item_id)
                if ch:
                    preview = ch.raw_text[:200] if ch.raw_text else ch.summary
                    r.content = f"第{ch.canonical_num}章 {ch.chapter_title}\n{preview}"
                    r.chapter_num = ch.canonical_num

        return sorted_results[:top_k]

    async def _retrieve_kg(
        self,
        book_id: int,
        query: str,
        top_k: int,
    ) -> List[RetrievalResult]:
        """知识图谱检索：实体名匹配 + 描述模糊匹配"""
        kg_results = []

        # 实体名精确/模糊匹配
        entities = await self._repo.search_entities(book_id, query, limit=top_k)
        for e in entities:
            score = 1.0 if query in e.name else 0.7
            kg_results.append(RetrievalResult(
                source="kg",
                item_type="entity",
                item_id=e.id,
                score=score,
                content=f"{e.name}({e.entity_type.value}): {e.description}",
            ))

        # 事件描述匹配
        events = await self._repo.get_events(book_id, limit=top_k * 2)
        for ev in events:
            if query in ev.description or any(query in p for p in ev.participants):
                score = 0.8 if query in ev.description else 0.5
                kg_results.append(RetrievalResult(
                    source="kg",
                    item_type="event",
                    item_id=ev.id,
                    score=score,
                    content=f"第{ev.chapter_num}章事件: {ev.description}",
                ))

        # 关系匹配
        rels = await self._repo.get_relationships(book_id, limit=top_k)
        for rel in rels:
            if query in rel.source_entity or query in rel.target_entity or query in rel.description:
                kg_results.append(RetrievalResult(
                    source="kg",
                    item_type="relationship",
                    item_id=rel.id,
                    score=0.6,
                    content=f"{rel.source_entity} -{rel.relation_type.value}-> {rel.target_entity}: {rel.description}",
                ))

        return sorted(kg_results, key=lambda x: x.score, reverse=True)[:top_k]

    async def build_bm25_index(self, book_id: int):
        """为书籍构建 BM25 索引"""
        chapters = await self._repo.get_chapters_by_book(book_id)
        self._chapter_cache = {}
        for ch in chapters:
            title_part = ch.chapter_title or ""
            summary_part = ch.summary or ""
            events_part = " ".join(ch.key_events) if ch.key_events else ""
            text_part = ch.raw_text or ""
            full_text = f"{title_part} {summary_part} {events_part} {text_part}"
            self._bm25.add_document(ch.id, full_text)
            self._chapter_cache[ch.id] = ch
        self._bm25.build()

    async def get_character_context(self, book_id: int, character_name: str) -> str:
        """获取角色的完整上下文（用于人物关系分析）"""
        parts = []

        # 实体信息
        entity = await self._repo.get_entity_by_name(book_id, character_name)
        if entity:
            parts.append(f"【角色档案】{entity.name}")
            parts.append(f"类型: {entity.entity_type.value}")
            parts.append(f"描述: {entity.description}")
            if entity.aliases:
                parts.append(f"别名: {', '.join(entity.aliases)}")
            parts.append(f"重要性: {entity.importance_score}/5")

        # 关系
        rels = await self._repo.get_relationships(book_id, entity_name=character_name)
        if rels:
            parts.append("【人际关系】")
            for rel in rels:
                parts.append(f"  {rel.source_entity} -{rel.relation_type.value}-> {rel.target_entity}: {rel.description}")

        # 状态变迁
        state_changes = await self._repo.get_state_changes(book_id, entity_name=character_name)
        if state_changes:
            parts.append("【状态变迁】")
            for sc in sorted(state_changes, key=lambda x: x.chapter_num):
                parts.append(f"  第{sc.chapter_num}章: {sc.field_name.value} [{sc.before_value}] -> [{sc.after_value}]")

        # 相关事件
        events = await self._repo.get_events(book_id, limit=50)
        char_events = [e for e in events if character_name in e.participants or character_name in e.related_entities]
        if char_events:
            parts.append("【参与事件】")
            for ev in sorted(char_events, key=lambda x: x.chapter_num)[:10]:
                parts.append(f"  第{ev.chapter_num}章: {ev.description}")

        return "\n".join(parts)

    async def get_world_context(self, book_id: int) -> str:
        """获取世界观上下文"""
        parts = ["【世界观设定】"]

        # 简化处理
        entities = await self._repo.list_entities(book_id, limit=100)

        locations = [e for e in entities if e.entity_type.value == "location"]
        if locations:
            parts.append("【地点】")
            for loc in locations[:15]:
                parts.append(f"  {loc.name}: {loc.description}")

        factions = [e for e in entities if e.entity_type.value == "faction"]
        if factions:
            parts.append("【势力】")
            for f in factions[:15]:
                parts.append(f"  {f.name}: {f.description}")

        realms = [e for e in entities if e.entity_type.value == "realm"]
        if realms:
            parts.append("【境界体系】")
            for r in realms[:15]:
                parts.append(f"  {r.name}: {r.description}")

        concepts = [e for e in entities if e.entity_type.value == "concept"]
        if concepts:
            parts.append("【核心概念】")
            for c in concepts[:15]:
                parts.append(f"  {c.name}: {c.description}")

        return "\n".join(parts)

    async def get_storyline_context(self, book_id: int) -> str:
        """获取剧情时间线上下文"""
        parts = ["【剧情时间线】"]

        events = await self._repo.get_events(book_id, min_importance=3, limit=50)
        for ev in sorted(events, key=lambda x: x.chapter_num):
            parts.append(f"第{ev.chapter_num}章 [{ev.event_type.value}] {ev.description}")
            if ev.participants:
                parts.append(f"  参与者: {', '.join(ev.participants)}")

        return "\n".join(parts)
