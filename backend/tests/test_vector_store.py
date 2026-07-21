import aiosqlite
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
async def sqlite_vector_store():
    db = await aiosqlite.connect(":memory:")
    await db.execute(
        """CREATE TABLE novel_vectors (
            owner_scope TEXT NOT NULL,
            book_id INTEGER NOT NULL,
            chapter_id INTEGER NOT NULL,
            knowledge_version TEXT NOT NULL,
            vector TEXT NOT NULL,
            payload TEXT NOT NULL,
            PRIMARY KEY(owner_scope, book_id, chapter_id, knowledge_version)
        )"""
    )
    await db.commit()
    from app.infrastructure.vectorstores.sqlite import SQLiteVectorStore

    try:
        yield SQLiteVectorStore(db)
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_sqlite_vector_store_filters_owner_book_version(sqlite_vector_store):
    from app.domain.repositories.vector_store import VectorRecord

    await sqlite_vector_store.upsert(
        [
            VectorRecord("user:1", 7, 1, "k1", [1.0, 0.0], {"text": "甲"}),
            VectorRecord("user:2", 7, 1, "k1", [1.0, 0.0], {"text": "乙"}),
            VectorRecord("user:1", 8, 1, "k1", [1.0, 0.0], {"text": "丙"}),
        ]
    )
    results = await sqlite_vector_store.search("user:1", 7, "k1", [1.0, 0.0], top_k=5)
    assert [item.payload["text"] for item in results] == ["甲"]


@pytest.mark.asyncio
async def test_disabled_store_has_no_fake_semantic_hits():
    from app.infrastructure.vectorstores.disabled import DisabledVectorStore

    store = DisabledVectorStore()
    assert (await store.health())["enabled"] is False
    assert await store.search("user:1", 7, "k1", [1.0], top_k=5) == []


@pytest.mark.asyncio
async def test_qdrant_adapter_sends_owner_and_version_filter():
    from app.domain.repositories.vector_store import VectorRecord
    from app.infrastructure.vectorstores.qdrant import QdrantVectorStore

    captured = {}

    def handler(request: httpx.Request):
        captured["body"] = request.read().decode()
        return httpx.Response(200, json={"result": [{"id": "1", "score": 0.9, "payload": {"text": "甲"}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        store = QdrantVectorStore("https://qdrant.test", "books", client=client)
        results = await store.search("user:1", 7, "k1", [1.0, 0.0], top_k=3)
        assert results[0].payload["text"] == "甲"
        assert "user:1" in captured["body"]
        assert "k1" in captured["body"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_sqlite_vector_store_supports_production_sqlalchemy_sessions():
    from app.domain.repositories.vector_store import VectorRecord
    from app.infrastructure.persistence.sqlite.schema import NovelVectorModel
    from app.infrastructure.vectorstores.sqlite import SQLiteVectorStore

    engine = create_engine("sqlite:///:memory:")
    NovelVectorModel.__table__.create(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    store = SQLiteVectorStore(session_factory=session_factory)

    await store.upsert([VectorRecord("user:1", 7, 1, "k1", [1.0, 0.0], {"text": "甲"})])
    results = await store.search("user:1", 7, "k1", [1.0, 0.0], top_k=1)

    assert results[0].payload["text"] == "甲"
    assert (await store.health())["enabled"] is True


@pytest.mark.asyncio
async def test_qdrant_adapter_rejects_malformed_result_shape():
    from app.domain.repositories.vector_store import VectorStoreUnavailable
    from app.infrastructure.vectorstores.qdrant import QdrantVectorStore

    def handler(_request: httpx.Request):
        return httpx.Response(200, json={"result": [{"payload": "not-an-object"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        store = QdrantVectorStore("https://qdrant.test", "books", client=client)
        with pytest.raises(VectorStoreUnavailable, match="invalid"):
            await store.search("user:1", 7, "k1", [1.0], top_k=3)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_pgvector_without_driver_is_typed_unavailable():
    from app.domain.repositories.vector_store import VectorStoreUnavailable
    from app.infrastructure.vectorstores.pgvector import PgVectorStore

    store = PgVectorStore()
    assert (await store.health())["enabled"] is False
    with pytest.raises(VectorStoreUnavailable):
        await store.upsert([])
