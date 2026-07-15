import pytest


@pytest.mark.asyncio
async def test_rate_limit_uses_a_bounded_in_memory_window_when_redis_is_unavailable():
    from app.core.redis_client import RedisClient

    client = RedisClient()
    client._redis = None
    client._memory_rate_windows.clear()

    first = await client.check_rate_limit("ratelimit:test:memory", max_requests=1, window_seconds=60)
    second = await client.check_rate_limit("ratelimit:test:memory", max_requests=1, window_seconds=60)

    assert first[0] is True
    assert second[0] is False
    assert second[1] == 0


@pytest.mark.asyncio
async def test_memory_rate_limit_caps_distinct_keys_when_redis_is_unavailable():
    from app.core.redis_client import RedisClient

    client = RedisClient()
    client._redis = None
    client._memory_rate_windows.clear()
    original_max_keys = type(client)._memory_rate_max_keys
    type(client)._memory_rate_max_keys = 2
    try:
        await client.check_rate_limit("ratelimit:test:one", max_requests=1, window_seconds=60)
        await client.check_rate_limit("ratelimit:test:two", max_requests=1, window_seconds=60)
        await client.check_rate_limit("ratelimit:test:three", max_requests=1, window_seconds=60)
    finally:
        type(client)._memory_rate_max_keys = original_max_keys

    assert len(client._memory_rate_windows) <= 2
