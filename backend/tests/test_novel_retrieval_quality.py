from types import SimpleNamespace

import aiosqlite
import pytest

from app.application.services.novel_understanding.retriever import RAGRetriever, RetrievalResult
from app.domain.entities.novel import NovelBook, NovelChapter, NovelRelationship, RelationType


@pytest.fixture
async def index_service():
    from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository
    from app.infrastructure.vectorstores.disabled import DisabledVectorStore
    from app.services.novel_understanding.embedding import EmbeddingAdapter
    from app.services.novel_understanding.index_service import NovelIndexService

    db = await aiosqlite.connect(":memory:")
    with open("app/database_migrations/novel_schema.sql", encoding="utf-8") as schema:
        await db.executescript(schema.read())
    repo = SqliteNovelRepository(db)
    book = await repo.save_book("user:1", NovelBook(book_url="https://index.test/book", book_name="索引书"))
    await repo.save_chapter(
        "user:1",
        NovelChapter(
            book_id=book.id,
            canonical_full="C1",
            canonical_num=1,
            chapter_title="雨夜",
            raw_text="林远走进青云宗，周宁在门前等他。",
        ),
    )
    await repo.save_chapter(
        "user:1",
        NovelChapter(
            book_id=book.id,
            canonical_full="C2",
            canonical_num=2,
            chapter_title="决战",
            raw_text="林远与周宁在山谷决战。",
        ),
    )
    service = NovelIndexService(
        repo=repo,
        vector_store=DisabledVectorStore(),
        embedding=EmbeddingAdapter(),
    )
    try:
        yield service, book.id
    finally:
        await db.close()


def test_retrieval_tracks_are_min_max_normalized_before_weighting():
    results = [
        RetrievalResult(source="bm25", item_type="chapter", item_id=1, score=2.0, content="a"),
        RetrievalResult(source="bm25", item_type="chapter", item_id=2, score=8.0, content="b"),
    ]

    normalized = RAGRetriever._normalize_scores(results)

    assert [item.score for item in normalized] == [0.0, 1.0]


@pytest.mark.asyncio
async def test_kg_relation_query_matches_entity_and_relation_tokens():
    class Repo:
        async def get_chapters_by_book(self, owner_scope, book_id, limit=100000):
            return []

        async def search_entities(self, owner_scope, book_id, query, limit=5):
            return []

        async def get_events(self, owner_scope, book_id, limit=5):
            return []

        async def get_relationships(self, owner_scope, book_id, limit=5):
            return [
                NovelRelationship(
                    book_id=book_id,
                    source_entity="李追远",
                    target_entity="玄真",
                    relation_type=RelationType.MASTER,
                    description="授业师父",
                )
            ]

        async def get_book_by_id(self, owner_scope, book_id):
            return SimpleNamespace(book_name="测试书")

        async def get_chapter_by_id(self, owner_scope, chapter_id):
            return None

    results = await RAGRetriever(Repo()).retrieve(
        "user:1", book_id=7, query="李追远的师父", top_k=5
    )

    assert any(item.item_type == "relationship" for item in results)


@pytest.mark.asyncio
async def test_index_result_exposes_empty_status_and_stage_timings(index_service):
    service, _ = index_service
    empty_book = await service.repo.save_book(
        "user:1", NovelBook(book_url="https://index.test/empty", book_name="空书")
    )

    result = await service.index_book("user:1", empty_book.id)

    assert result.status == "no_chapters"
    assert result.no_chapters is True
    assert result.timings_ms["total"] >= 0


@pytest.mark.asyncio
async def test_index_batches_vector_health_embedding_and_upsert(index_service):
    service, book_id = index_service

    class Embedding:
        model = "batch-test"

        def __init__(self):
            self.calls = []

        async def embed_batch(self, texts):
            self.calls.append(list(texts))
            return [
                SimpleNamespace(
                    semantic=True,
                    vector=[1.0, 0.0],
                    model=self.model,
                    dimension=2,
                )
                for _ in texts
            ]

    class Store:
        retry_disabled = False

        def __init__(self):
            self.health_calls = 0
            self.upsert_calls = 0
            self.records = []

        async def health(self):
            self.health_calls += 1
            return {"enabled": True}

        async def delete_chapter(self, *args):
            return 0

        async def upsert(self, records):
            self.upsert_calls += 1
            self.records.extend(records)
            return len(records)

    embedding = Embedding()
    store = Store()
    service.embedding = embedding
    service.vector_store = store

    result = await service.index_book("user:1", book_id)

    assert result.failed_chapters == 0
    assert len(embedding.calls) == 1
    assert store.health_calls == 1
    assert store.upsert_calls == 1
    assert len(store.records) == 3
