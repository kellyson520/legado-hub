"""
内存缓存实现 - 小 VPS 零依赖方案

特点：
- 纯 Python 字典实现
- 支持 TTL 自动过期
- 线程安全
- 内存上限保护（LRU 淘汰）
"""

import threading
import time
from typing import Any, Optional, Dict
from collections import OrderedDict

from .abstract import CacheProvider


class MemoryCacheProvider(CacheProvider):
    """内存缓存提供者"""
    
    def __init__(self, max_size: int = 10000):
        self._data: Dict[str, Any] = {}
        self._expires: Dict[str, float] = {}
        self._counters: Dict[str, int] = {}
        self._lock = threading.RLock()
        self._max_size = max_size
    
    def _is_expired(self, key: str) -> bool:
        if key not in self._expires:
            return False
        return time.time() > self._expires[key]
    
    def _cleanup_expired(self):
        """清理过期项（惰性清理）"""
        now = time.time()
        expired_keys = [k for k, exp in self._expires.items() if now > exp]
        for k in expired_keys:
            self._data.pop(k, None)
            self._expires.pop(k, None)
    
    async def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._data:
                return None
            if self._is_expired(key):
                self._data.pop(key, None)
                self._expires.pop(key, None)
                return None
            return self._data[key]
    
    async def set(self, key: str, value: Any, expire: int = 3600) -> bool:
        with self._lock:
            # 内存保护：如果超限，清理最旧的项
            if len(self._data) >= self._max_size and key not in self._data:
                self._cleanup_expired()
                if len(self._data) >= self._max_size:
                    # LRU 淘汰最旧的
                    oldest = next(iter(self._data))
                    self._data.pop(oldest, None)
                    self._expires.pop(oldest, None)
            
            self._data[key] = value
            if expire > 0:
                self._expires[key] = time.time() + expire
            return True
    
    async def delete(self, key: str) -> bool:
        with self._lock:
            self._data.pop(key, None)
            self._expires.pop(key, None)
            return True
    
    async def exists(self, key: str) -> bool:
        with self._lock:
            if key not in self._data:
                return False
            if self._is_expired(key):
                self._data.pop(key, None)
                self._expires.pop(key, None)
                return False
            return True
    
    async def increment(self, key: str, amount: int = 1, expire: int = 86400) -> int:
        with self._lock:
            current = self._counters.get(key, 0)
            new_val = current + amount
            self._counters[key] = new_val
            if expire > 0:
                self._expires[key] = time.time() + expire
            return new_val
    
    async def get_counter(self, key: str) -> int:
        with self._lock:
            if self._is_expired(key):
                self._counters.pop(key, None)
                self._expires.pop(key, None)
                return 0
            return self._counters.get(key, 0)
    
    async def reset_counter(self, key: str) -> bool:
        with self._lock:
            self._counters.pop(key, None)
            self._expires.pop(key, None)
            return True
