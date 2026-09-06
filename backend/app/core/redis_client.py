"""
Redis 客户端封装 — 缓存、限流、队列、配额

职责：
- 连接管理（自动重连）
- 降级策略（Redis 不可用时自动降级为无限制/空缓存）
- 统一日志（禁止缺失日志）
"""

import json
import time
from collections import deque
from threading import Lock
from typing import Optional, Any, List
import redis.asyncio as redis
from .config import settings
from .logging import get_logger

logger = get_logger("redis")


class RedisClient:
    """Redis 客户端封装 - 支持缓存、限流、队列"""

    _instance: Optional["RedisClient"] = None
    _redis: Optional[redis.Redis] = None
    _memory_rate_windows: dict[str, deque[float]] = {}
    _memory_rate_lock = Lock()
    _memory_rate_max_keys = 10_000

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def connect(self):
        """建立 Redis 连接"""
        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                    health_check_interval=30
                )
                await self._redis.ping()
                logger.info("[Redis] 连接成功", extra={"action": "redis_connected", "url": settings.REDIS_URL})
            except Exception as e:
                logger.warning(
                    f"[Redis] 连接失败，将使用内存降级: {type(e).__name__}: {e}",
                    extra={"action": "redis_connect_failed", "error": str(e)}
                )
                self._redis = None
        return self._redis

    async def disconnect(self):
        """关闭连接"""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("[Redis] 连接已关闭", extra={"action": "redis_disconnected"})

    @property
    def is_connected(self) -> bool:
        return self._redis is not None

    # ==================== Cache Operations ====================

    async def get(self, key: str) -> Optional[str]:
        if not self._redis:
            return None
        try:
            return await self._redis.get(key)
        except Exception as e:
            logger.warning(f"[Redis] get error: {key} - {e}", extra={"action": "redis_get_error", "key": key, "error": str(e)})
            return None

    async def get_json(self, key: str) -> Optional[Any]:
        data = await self.get(key)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError as e:
                logger.warning(f"[Redis] JSON 解析失败: {key} - {e}", extra={"action": "redis_json_parse_error", "key": key, "error": str(e)})
        return None

    async def set(self, key: str, value: str, expire: int = 3600):
        if not self._redis:
            return False
        try:
            await self._redis.set(key, value, ex=expire)
            return True
        except Exception as e:
            logger.warning(f"[Redis] set error: {key} - {e}", extra={"action": "redis_set_error", "key": key, "error": str(e)})
            return False

    async def set_json(self, key: str, value: Any, expire: int = 3600):
        return await self.set(key, json.dumps(value, ensure_ascii=False, default=str), expire)

    async def delete(self, key: str):
        if not self._redis:
            return 0
        try:
            return await self._redis.delete(key)
        except Exception as e:
            logger.warning(f"[Redis] delete error: {key} - {e}", extra={"action": "redis_delete_error", "key": key, "error": str(e)})
            return 0

    async def exists(self, key: str) -> bool:
        if not self._redis:
            return False
        try:
            return await self._redis.exists(key) > 0
        except Exception as e:
            logger.debug(f"[Redis] exists error: {key} - {e}", extra={"action": "redis_exists_error", "key": key, "error": str(e)})
            return False

    # ==================== Rate Limiting ====================

    async def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
        """
        滑动窗口限流检查
        Returns: (allowed, remaining, reset_after)
        """
        if not self._redis:
            # Redis 不可用时仍提供进程内滑动窗口，避免公开 API 无限放行。
            return self._check_memory_rate_limit(key, max_requests, window_seconds)

        try:
            now = await self._redis.time()
            now_ms = now[0] * 1000 + now[1] // 1000
            window_start = now_ms - window_seconds * 1000

            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.zadd(key, {str(now_ms): now_ms})
            pipe.expire(key, window_seconds + 1)

            results = await pipe.execute()
            current_count = results[1]

            if current_count >= max_requests:
                await self._redis.zrem(key, str(now_ms))
                oldest = await self._redis.zrange(key, 0, 0, withscores=True)
                reset_after = int((oldest[0][1] + window_seconds * 1000 - now_ms) / 1000) if oldest else window_seconds
                return False, 0, max(0, reset_after)

            remaining = max_requests - current_count - 1
            return True, remaining, 0

        except Exception as e:
            logger.warning(
                f"[Redis] rate limit error: {key} - {e}",
                extra={"action": "redis_rate_limit_error", "key": key, "error": str(e)}
            )
            return self._check_memory_rate_limit(key, max_requests, window_seconds)

    @classmethod
    def _check_memory_rate_limit(cls, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
        now = time.monotonic()
        with cls._memory_rate_lock:
            if key not in cls._memory_rate_windows and len(cls._memory_rate_windows) >= cls._memory_rate_max_keys:
                for candidate_key, candidate_window in list(cls._memory_rate_windows.items()):
                    while candidate_window and candidate_window[0] <= now - window_seconds:
                        candidate_window.popleft()
                    if not candidate_window:
                        cls._memory_rate_windows.pop(candidate_key, None)
                while len(cls._memory_rate_windows) >= cls._memory_rate_max_keys:
                    cls._memory_rate_windows.pop(next(iter(cls._memory_rate_windows)), None)
            window = cls._memory_rate_windows.setdefault(key, deque())
            boundary = now - window_seconds
            while window and window[0] <= boundary:
                window.popleft()
            if len(window) >= max_requests:
                reset_after = max(0, int(window_seconds - (now - window[0]))) if window else window_seconds
                return False, 0, reset_after
            window.append(now)
            return True, max(0, max_requests - len(window)), 0

    # ==================== Quota Tracking ====================

    async def increment_quota(self, api_key_id: int, metric: str, amount: int = 1, ttl_seconds: int = 86400) -> int:
        """
        原子增加配额计数
        metric: fetch_count, ai_chars, storage_mb
        """
        if not self._redis:
            return 0

        try:
            key = f"quota:{api_key_id}:{metric}"
            new_val = await self._redis.incrby(key, amount)
            await self._redis.expire(key, ttl_seconds)
            return new_val
        except Exception as e:
            logger.warning(
                f"[Redis] quota increment error: key_id={api_key_id}, metric={metric} - {e}",
                extra={"action": "redis_quota_incr_error", "api_key_id": api_key_id, "metric": metric, "error": str(e)}
            )
            return 0

    async def get_quota(self, api_key_id: int, metric: str) -> int:
        """获取当前配额使用量"""
        if not self._redis:
            return 0
        try:
            key = f"quota:{api_key_id}:{metric}"
            val = await self._redis.get(key)
            return int(val) if val else 0
        except Exception as e:
            logger.debug(
                f"[Redis] quota get error: key_id={api_key_id}, metric={metric} - {e}",
                extra={"action": "redis_quota_get_error", "api_key_id": api_key_id, "metric": metric, "error": str(e)}
            )
            return 0

    async def reset_quota(self, api_key_id: int, metric: str):
        """重置配额计数"""
        if not self._redis:
            return
        try:
            key = f"quota:{api_key_id}:{metric}"
            await self._redis.delete(key)
            logger.debug(
                f"[Redis] 配额重置: key_id={api_key_id}, metric={metric}",
                extra={"action": "redis_quota_reset", "api_key_id": api_key_id, "metric": metric}
            )
        except Exception as e:
            logger.warning(
                f"[Redis] quota reset error: key_id={api_key_id}, metric={metric} - {e}",
                extra={"action": "redis_quota_reset_error", "api_key_id": api_key_id, "metric": metric, "error": str(e)}
            )

    # ==================== Task Queue ====================

    async def enqueue_task(self, queue_name: str, task_data: dict) -> bool:
        """将任务加入队列"""
        if not self._redis:
            return False
        try:
            await self._redis.lpush(queue_name, json.dumps(task_data, ensure_ascii=False, default=str))
            return True
        except Exception as e:
            logger.warning(f"[Redis] enqueue error: {queue_name} - {e}", extra={"action": "redis_enqueue_error", "queue": queue_name, "error": str(e)})
            return False

    async def dequeue_task(self, queue_name: str, timeout: int = 5) -> Optional[dict]:
        """从队列取出任务（阻塞式）"""
        if not self._redis:
            return None
        try:
            result = await self._redis.brpop(queue_name, timeout=timeout)
            if result:
                return json.loads(result[1])
            return None
        except Exception as e:
            logger.warning(f"[Redis] dequeue error: {queue_name} - {e}", extra={"action": "redis_dequeue_error", "queue": queue_name, "error": str(e)})
            return None

    async def get_queue_length(self, queue_name: str) -> int:
        """获取队列长度"""
        if not self._redis:
            return 0
        try:
            return await self._redis.llen(queue_name)
        except Exception as e:
            logger.debug(f"[Redis] queue length error: {queue_name} - {e}", extra={"action": "redis_queue_length_error", "queue": queue_name, "error": str(e)})
            return 0

    # ==================== Source Cache ====================

    async def cache_source_check(self, source_url: str, status: dict, expire: int = 3600):
        """缓存源可用性检查结果"""
        key = f"source_check:{source_url}"
        await self.set_json(key, status, expire)

    async def get_cached_source_check(self, source_url: str) -> Optional[dict]:
        key = f"source_check:{source_url}"
        return await self.get_json(key)

    async def invalidate_source_cache(self, source_url: str):
        key = f"source_check:{source_url}"
        await self.delete(key)


# 全局实例
redis_client = RedisClient()
