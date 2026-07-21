import pytest


@pytest.mark.asyncio
async def test_cache_key_never_reuses_another_owner_or_knowledge_version():
    from app.application.services.novel_cache_service import NovelCacheService
    from app.infrastructure.cache.memory_cache import MemoryCacheProvider

    cache = NovelCacheService(MemoryCacheProvider())
    first = cache.key(
        owner_scope="user:1", book_id=9, knowledge_version="k1", model="m",
        task_type="chat", query="林远是谁", prompt_version="p1", toolset_version="t1"
    )
    second = cache.key(
        owner_scope="user:2", book_id=9, knowledge_version="k1", model="m",
        task_type="chat", query="林远是谁", prompt_version="p1", toolset_version="t1"
    )
    third = cache.key(
        owner_scope="user:1", book_id=9, knowledge_version="k2", model="m",
        task_type="chat", query="林远是谁", prompt_version="p1", toolset_version="t1"
    )
    assert len({first, second, third}) == 3


@pytest.mark.asyncio
async def test_cache_stores_only_successful_results_and_reports_hits():
    from app.application.services.novel_cache_service import NovelCacheService
    from app.infrastructure.cache.memory_cache import MemoryCacheProvider

    cache = NovelCacheService(MemoryCacheProvider())
    calls = 0

    async def successful_factory():
        nonlocal calls
        calls += 1
        return {"answer": "已缓存"}

    first = await cache.get_or_set("novel:test", successful_factory)
    second = await cache.get_or_set("novel:test", successful_factory)
    assert first == ({"answer": "已缓存"}, False)
    assert second == ({"answer": "已缓存"}, True)
    assert calls == 1

    async def failing_factory():
        raise RuntimeError("provider down")

    with pytest.raises(RuntimeError):
        await cache.get_or_set("novel:failed", failing_factory)
    assert await cache._cache.get("novel:failed") is None
