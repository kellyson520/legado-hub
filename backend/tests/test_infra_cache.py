"""
infrastructure/cache/memory_cache.py 单元测试

覆盖 MemoryCacheProvider 的所有方法：
- get
- set
- delete
- exists
- increment
- get_counter
- reset_counter
"""

import pytest
import time
from app.infrastructure.cache.memory_cache import MemoryCacheProvider


class TestMemoryCacheBasic:
    """缓存基本操作测试"""

    async def test_set_and_get(self, cache_provider):
        """验证设置和获取缓存值"""
        await cache_provider.set("key1", "value1")
        result = await cache_provider.get("key1")
        assert result == "value1"

    async def test_get_nonexistent_key(self, cache_provider):
        """验证获取不存在的 key 返回 None"""
        result = await cache_provider.get("nonexistent")
        assert result is None

    async def test_set_overwrites_existing_value(self, cache_provider):
        """验证 set 覆盖已有值"""
        await cache_provider.set("key1", "value1")
        await cache_provider.set("key1", "value2")
        result = await cache_provider.get("key1")
        assert result == "value2"

    async def test_set_with_complex_value(self, cache_provider):
        """验证缓存复杂类型值（字典、列表）"""
        data = {"name": "test", "items": [1, 2, 3]}
        await cache_provider.set("complex", data)
        result = await cache_provider.get("complex")
        assert result == data


class TestMemoryCacheExpiry:
    """缓存过期测试"""

    async def test_expired_key_returns_none(self, cache_provider):
        """验证过期 key 返回 None"""
        # 设置 1 秒过期
        await cache_provider.set("expiring", "value", expire=1)
        result = await cache_provider.get("expiring")
        assert result == "value"

        # 等待过期
        time.sleep(1.5)
        result = await cache_provider.get("expiring")
        assert result is None

    async def test_set_with_zero_expire_no_expiry(self, cache_provider):
        """验证 expire=0 时不过期"""
        await cache_provider.set("no_expire", "value", expire=0)
        time.sleep(0.1)
        result = await cache_provider.get("no_expire")
        assert result == "value"


class TestMemoryCacheDelete:
    """缓存删除测试"""

    async def test_delete_existing_key(self, cache_provider):
        """验证删除已存在的 key"""
        await cache_provider.set("del_key", "value")
        result = await cache_provider.delete("del_key")
        assert result is True
        assert await cache_provider.get("del_key") is None

    async def test_delete_nonexistent_key(self, cache_provider):
        """验证删除不存在的 key 仍返回 True"""
        result = await cache_provider.delete("nonexistent")
        assert result is True


class TestMemoryCacheExists:
    """缓存存在性检查测试"""

    async def test_exists_returns_true_for_existing_key(self, cache_provider):
        """验证已存在的 key 返回 True"""
        await cache_provider.set("exists_key", "value")
        assert await cache_provider.exists("exists_key") is True

    async def test_exists_returns_false_for_nonexistent_key(self, cache_provider):
        """验证不存在的 key 返回 False"""
        assert await cache_provider.exists("no_such_key") is False

    async def test_exists_returns_false_for_expired_key(self, cache_provider):
        """验证过期 key 返回 False"""
        await cache_provider.set("exp_exists", "value", expire=1)
        time.sleep(1.5)
        assert await cache_provider.exists("exp_exists") is False


class TestMemoryCacheCounter:
    """缓存计数器测试"""

    async def test_increment_from_zero(self, cache_provider):
        """验证从 0 递增"""
        result = await cache_provider.increment("counter1")
        assert result == 1

    async def test_increment_multiple_times(self, cache_provider):
        """验证多次递增"""
        await cache_provider.increment("counter2")
        await cache_provider.increment("counter2")
        await cache_provider.increment("counter2")
        result = await cache_provider.increment("counter2")
        assert result == 4

    async def test_increment_with_custom_amount(self, cache_provider):
        """验证自定义递增步长"""
        result = await cache_provider.increment("counter3", amount=10)
        assert result == 10

    async def test_get_counter(self, cache_provider):
        """验证获取计数器值"""
        await cache_provider.increment("counter4", amount=5)
        result = await cache_provider.get_counter("counter4")
        assert result == 5

    async def test_get_counter_nonexistent(self, cache_provider):
        """验证获取不存在的计数器返回 0"""
        result = await cache_provider.get_counter("nonexistent_counter")
        assert result == 0

    async def test_reset_counter(self, cache_provider):
        """验证重置计数器"""
        await cache_provider.increment("counter5", amount=100)
        result = await cache_provider.reset_counter("counter5")
        assert result is True
        assert await cache_provider.get_counter("counter5") == 0

    async def test_counter_expiry(self, cache_provider):
        """验证计数器过期后自动重置"""
        await cache_provider.increment("exp_counter", amount=10, expire=1)
        time.sleep(1.5)
        result = await cache_provider.get_counter("exp_counter")
        assert result == 0


class TestMemoryCacheMaxSize:
    """缓存容量保护测试"""

    async def test_lru_eviction_when_full(self):
        """验证超出容量时淘汰最早的数据"""
        cache = MemoryCacheProvider(max_size=3)

        await cache.set("key1", "v1")
        await cache.set("key2", "v2")
        await cache.set("key3", "v3")
        # 容量已满，再插入应淘汰 key1
        await cache.set("key4", "v4")

        # key1 应已被淘汰
        assert await cache_provider_get(cache, "key1") is None
        assert await cache.get("key4") == "v4"


async def cache_provider_get(cache, key):
    """辅助函数：调用 cache.get"""
    return await cache.get(key)
