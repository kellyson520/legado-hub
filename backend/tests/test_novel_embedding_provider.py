import pytest


class FakeEmbeddingPlatform:
    def __init__(self):
        self.calls = []

    async def invoke_novel_embedding(self, *, owner_scope, model, payload, quota_scope):
        self.calls.append((owner_scope, model, payload, quota_scope))
        return {
            "provider_name": "fake-embedding",
            "model": model,
            "data": [
                {"index": index, "embedding": [float(index), 1.0]}
                for index, _ in enumerate(payload["input"])
            ],
            "usage": {"input_tokens": 4, "total_tokens": 4},
        }


@pytest.mark.asyncio
async def test_embedding_adapter_uses_provider_and_honors_batch_size():
    from app.services.novel_understanding.embedding import EmbeddingAdapter

    platform = FakeEmbeddingPlatform()
    adapter = EmbeddingAdapter(
        provider=platform,
        owner_scope="user:1",
        model="embed-model",
        batch_size=2,
        quota_scope=("user", "1"),
    )

    results = await adapter.embed_batch(["甲", "乙", "丙"])

    assert [result.source for result in results] == ["provider", "provider", "provider"]
    assert [result.model for result in results] == ["embed-model"] * 3
    assert [result.dimension for result in results] == [2] * 3
    assert all(result.semantic is True for result in results)
    assert [len(call[2]["input"]) for call in platform.calls] == [2, 1]


@pytest.mark.asyncio
async def test_hash_embedding_is_explicitly_non_semantic_fallback():
    from app.services.novel_understanding.embedding import EmbeddingAdapter

    result = await EmbeddingAdapter().embed("测试文本")

    assert result.source == "local_hash"
    assert result.semantic is False


@pytest.mark.asyncio
async def test_embedding_adapter_reuses_novel_cache_and_records_hit():
    from app.application.services.novel_cache_service import NovelCacheService
    from app.infrastructure.cache.memory_cache import MemoryCacheProvider
    from app.services.novel_understanding.embedding import EmbeddingAdapter

    platform = FakeEmbeddingPlatform()
    cache = NovelCacheService(MemoryCacheProvider())
    adapter = EmbeddingAdapter(
        provider=platform,
        owner_scope="user:1",
        book_id=7,
        knowledge_version="k1",
        model="embed-model",
        cache_service=cache,
    )

    first = await adapter.embed("同一段正文")
    second = await adapter.embed("同一段正文")

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert len(platform.calls) == 1
    assert cache.stats()["hits"] == 1


@pytest.mark.asyncio
async def test_embedding_adapter_accepts_a_simple_provider_callable():
    from app.services.novel_understanding.embedding import EmbeddingAdapter

    async def provider(texts):
        return {
            "model": "callable-model",
            "data": [{"index": 0, "embedding": [0.5, 0.5]} for _ in texts],
        }

    result = await EmbeddingAdapter(provider=provider).embed("正文")

    assert result.vector == [0.5, 0.5]
    assert result.model == "callable-model"
