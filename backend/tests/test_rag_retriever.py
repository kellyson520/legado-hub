"""
RAG 检索器 + Prompt 构建器 + Embedding 测试
"""

import pytest
import aiosqlite

from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository
from app.domain.entities.novel import (
    NovelBook, NovelChapter, NovelEntity, NovelEvent, NovelRelationship,
    NovelStateChange, EntityType, RelationType, EventType, StateField,
)
from app.domain.value_objects import ChapterType
from app.services.novel_understanding.bm25_index import BM25Index
from app.services.novel_understanding.embedding import EmbeddingAdapter
from app.services.novel_understanding.retriever import RAGRetriever, RetrievalResult
from app.services.novel_understanding.prompt_builder import PromptBuilder
from app.services.novel_understanding.summarizer import HierarchicalSummary


class TestBM25Index:
    """BM25 索引测试"""

    def test_add_and_search(self):
        idx = BM25Index()
        idx.add_document(1, "第一章 林远初入宗门")
        idx.add_document(2, "第二章 周宁修炼剑法")
        idx.build()

        results = idx.search("林远")
        assert len(results) == 1
        assert results[0][0] == 1

    def test_search_multiple(self):
        idx = BM25Index()
        idx.add_document(1, "林远大战周宁")
        idx.add_document(2, "林远修炼")
        idx.add_document(3, "其他内容")
        idx.build()

        results = idx.search("林远")
        assert len(results) == 2
        # 包含两个词的文档应该得分更高
        doc_ids = [r[0] for r in results]
        assert 1 in doc_ids
        assert 2 in doc_ids

    def test_tokenize(self):
        tokens = BM25Index._tokenize("第一章 林远初入宗门")
        assert "林远" in tokens
        assert "宗门" in tokens


class TestEmbeddingAdapter:
    """Embedding 适配器测试"""

    @pytest.mark.asyncio
    async def test_local_hash_embedding(self):
        adapter = EmbeddingAdapter()
        result = await adapter.embed("测试文本")
        assert result.source == "local_hash"
        assert len(result.vector) == EmbeddingAdapter.DIMENSION

    @pytest.mark.asyncio
    async def test_embedding_consistency(self):
        adapter = EmbeddingAdapter()
        r1 = await adapter.embed("相同文本")
        r2 = await adapter.embed("相同文本")
        assert r1.vector == r2.vector  # 确定性

    def test_cosine_similarity_same(self):
        v = [1.0, 0.0, 0.0]
        sim = EmbeddingAdapter.cosine_similarity(v, v)
        assert sim == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        sim = EmbeddingAdapter.cosine_similarity(a, b)
        assert sim == pytest.approx(0.0)


class TestRAGRetriever:
    """RAG 检索器集成测试"""

    @pytest.fixture
    async def retriever(self):
        db = await aiosqlite.connect(":memory:")
        with open("app/database_migrations/novel_schema.sql", encoding="utf-8") as f:
            await db.executescript(f.read())
        repo = SqliteNovelRepository(db)
        retriever = RAGRetriever(repo)
        yield retriever
        await db.close()

    async def test_build_index_and_retrieve(self, retriever):
        # 创建测试数据
        book = await retriever._repo.save_book(NovelBook(book_url="https://test", book_name="测试书"))
        await retriever._repo.save_chapter(NovelChapter(book_id=book.id, canonical_full="C1", canonical_num=1, chapter_title="林远入宗", summary="林远加入青云宗"))
        await retriever._repo.save_chapter(NovelChapter(book_id=book.id, canonical_full="C2", canonical_num=2, chapter_title="周宁出现", summary="周宁修炼剑法"))

        await retriever.build_bm25_index(book.id)
        results = await retriever.retrieve(book.id, "林远", top_k=5)
        assert len(results) > 0
        assert any("林远" in r.content for r in results)

    async def test_character_context(self, retriever):
        book = await retriever._repo.save_book(NovelBook(book_url="https://test", book_name="测试书"))
        await retriever._repo.save_entity(NovelEntity(book_id=book.id, name="林远", entity_type=EntityType.CHARACTER, description="主角"))
        await retriever._repo.save_relationship(NovelRelationship(book_id=book.id, source_entity="林远", target_entity="周宁", relation_type=RelationType.ALLY))
        await retriever._repo.save_state_change(NovelStateChange(book_id=book.id, entity_name="林远", chapter_num=1, field_name=StateField.REALM, before_value="炼气", after_value="筑基"))

        ctx = await retriever.get_character_context(book.id, "林远")
        assert "林远" in ctx
        assert "主角" in ctx
        assert "周宁" in ctx
        assert "炼气" in ctx
        assert "筑基" in ctx

    async def test_world_context(self, retriever):
        book = await retriever._repo.save_book(NovelBook(book_url="https://test", book_name="测试书"))
        await retriever._repo.save_entity(NovelEntity(book_id=book.id, name="青云宗", entity_type=EntityType.FACTION, description="修真大派"))
        await retriever._repo.save_entity(NovelEntity(book_id=book.id, name="炼气期", entity_type=EntityType.REALM, description="入门境界"))

        ctx = await retriever.get_world_context(book.id)
        assert "青云宗" in ctx
        assert "炼气期" in ctx

    async def test_storyline_context(self, retriever):
        book = await retriever._repo.save_book(NovelBook(book_url="https://test", book_name="测试书"))
        await retriever._repo.save_event(NovelEvent(book_id=book.id, chapter_id=1, chapter_num=1, event_type=EventType.BATTLE, description="宗门大比", importance=5))

        ctx = await retriever.get_storyline_context(book.id)
        assert "宗门大比" in ctx


@pytest.mark.asyncio
async def test_scoped_retrieval_returns_evidence_and_never_uses_hash_vectors():
    db = await aiosqlite.connect(":memory:")
    with open("app/database_migrations/novel_schema.sql", encoding="utf-8") as schema:
        await db.executescript(schema.read())
    try:
        from app.domain.entities.novel import NovelBook, NovelChapter
        from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository
        from app.infrastructure.vectorstores.disabled import DisabledVectorStore

        repo = SqliteNovelRepository(db)
        book = await repo.save_book("user:1", NovelBook(book_url="https://rag.test", book_name="检索书"))
        await repo.save_chapter(
            "user:1",
            NovelChapter(
                book_id=book.id,
                canonical_full="C1",
                canonical_num=1,
                chapter_title="离开",
                raw_text="林远离开青云宗，周宁在城门送别。",
            ),
        )
        retriever = RAGRetriever(repo, vector_store=DisabledVectorStore())
        await retriever.build_bm25_index("user:1", book.id, knowledge_version="k1")
        results = await retriever.retrieve("user:1", book_id=book.id, query="林远离开", top_k=5)

        assert results
        assert all(result.owner_scope == "user:1" for result in results)
        assert all(result.chapter_num >= 0 and result.evidence for result in results)
        assert {result.source for result in results} <= {"bm25", "vector", "kg"}
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_vector_memory_payload_maps_type_record_key_and_citation():
    from app.domain.repositories.vector_store import VectorRecord

    class Repo:
        async def get_chapters_by_book(self, owner_scope, book_id, limit=100000):
            return []

        async def get_book_by_id(self, owner_scope, book_id):
            return type("Book", (), {"book_name": "记忆书"})()

        async def get_chapter_by_id(self, owner_scope, chapter_id):
            return None

        async def search_entities(self, owner_scope, book_id, query, limit=5):
            return []

        async def get_events(self, owner_scope, book_id, limit=5):
            return []

        async def get_relationships(self, owner_scope, book_id, limit=5):
            return []

    class Embedding:
        async def embed(self, query):
            return type("Embedding", (), {"semantic": True, "vector": [1.0]})()

    class Store:
        async def search(self, owner_scope, book_id, knowledge_version, query_vector, top_k):
            return [
                VectorRecord(
                    owner_scope,
                    book_id,
                    0,
                    knowledge_version,
                    [],
                    {
                        "memory_type": "entity",
                        "record_key": "entity:item:玄天剑",
                        "item_id": 42,
                        "chapter_id": 0,
                        "chapter_num": 0,
                        "card": "实体|名称: 玄天剑",
                        "evidence": [{"chapter_id": 0, "text": "江轩取出玄天剑"}],
                    },
                    0.95,
                    "entity:item:玄天剑",
                )
            ]

    results = await RAGRetriever(Repo(), embedding=Embedding(), vector_store=Store()).retrieve(
        "user:1", 7, "玄天剑", top_k=5, knowledge_version="k1"
    )

    memory = next(item for item in results if item.source == "vector")
    assert memory.item_type == "entity"
    assert memory.item_id == 42
    assert memory.record_key == "entity:item:玄天剑"
    assert memory.chapter_num == 0
    assert "江轩取出玄天剑" in memory.evidence
    assert memory.citation["chapter_id"] == 0


class TestPromptBuilder:
    """Prompt 构建器测试"""

    def test_build_character_prompt(self):
        book = NovelBook(book_name="测试书")
        system, user = PromptBuilder.build_character_prompt(book)
        assert "人物关系" in system
        assert "测试书" in user

    def test_build_character_prompt_with_summary(self):
        book = NovelBook(book_name="测试书")
        summary = HierarchicalSummary(
            book_id=1,
            entity_cards=[{"name": "林远", "description": "主角"}],
        )
        system, user = PromptBuilder.build_character_prompt(book, summary=summary)
        assert "林远" in user

    def test_build_chat_prompt(self):
        book = NovelBook(book_name="测试书")
        system, user = PromptBuilder.build_chat_prompt(book, "林远是谁？")
        assert "小说阅读助手" in system
        assert "林远是谁" in user

    def test_build_world_prompt(self):
        book = NovelBook(book_name="测试书")
        system, user = PromptBuilder.build_world_prompt(book)
        assert "世界观" in system

    def test_build_storyline_prompt(self):
        book = NovelBook(book_name="测试书")
        system, user = PromptBuilder.build_storyline_prompt(book)
        assert "剧情时间线" in system

    def test_trim_long_text(self):
        long_text = "x" * 20000
        trimmed = PromptBuilder._trim(long_text)
        assert len(trimmed) <= PromptBuilder.MAX_PROMPT_CHARS + 20
        assert "截断" in trimmed
