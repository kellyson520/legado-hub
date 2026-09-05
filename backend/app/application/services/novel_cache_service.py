from __future__ import annotations

import asyncio
import inspect
import json
from collections import OrderedDict, defaultdict
from hashlib import sha256
from threading import Lock
from typing import Any, Awaitable, Callable

from app.application.ports.cache import CacheProvider


class NovelCacheService:
    """Owner-aware cache facade with deterministic invalidation and metrics."""

    def __init__(
        self,
        cache: CacheProvider,
        *,
        default_ttl: int = 3600,
        max_book_keys: int = 4096,
    ):
        self._cache = cache
        self._default_ttl = default_ttl
        self._max_book_keys = max(1, int(max_book_keys))
        self._book_keys: dict[tuple[str, int], OrderedDict[str, None]] = defaultdict(OrderedDict)
        self._fill_locks: dict[str, tuple[asyncio.Lock, int]] = {}
        self._fill_locks_guard = Lock()
        self._stats = {"hits": 0, "misses": 0, "writes": 0, "failed": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}

    def key(
        self,
        *,
        owner_scope: str,
        book_id: int | None,
        knowledge_version: str,
        model: str,
        task_type: str,
        query: str,
        prompt_version: str,
        toolset_version: str,
        chapter_id: int | None = None,
        entrypoint: str = "",
        conversation_id: str = "",
    ) -> str:
        payload = json.dumps(
            {
                "owner_scope": owner_scope,
                "book_id": book_id,
                "knowledge_version": knowledge_version,
                "model": model,
                "task_type": task_type,
                "query_hash": sha256(query.encode("utf-8")).hexdigest(),
                "prompt_version": prompt_version,
                "toolset_version": toolset_version,
                "chapter_id": chapter_id,
                "entrypoint": entrypoint,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        key = "novel:v1:" + sha256(payload.encode("utf-8")).hexdigest()
        if book_id is not None:
            book_keys = self._book_keys[(owner_scope, int(book_id))]
            book_keys[key] = None
            book_keys.move_to_end(key)
            while len(book_keys) > self._max_book_keys:
                book_keys.popitem(last=False)
        return key

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any | Awaitable[Any]],
        *,
        ttl: int | None = None,
    ) -> tuple[Any, bool]:
        cached = await self._cache.get(key)
        if cached is not None:
            self._stats["hits"] += 1
            return cached, True
        self._stats["misses"] += 1
        fill_lock = self._acquire_fill_lock(key)
        try:
            async with fill_lock[0]:
                cached = await self._cache.get(key)
                if cached is not None:
                    self._stats["hits"] += 1
                    return cached, True
                try:
                    value = factory()
                    if inspect.isawaitable(value):
                        value = await value
                except Exception:
                    self._stats["failed"] += 1
                    raise
                if value is not None:
                    await self._cache.set(key, value, expire=self._default_ttl if ttl is None else ttl)
                    self._stats["writes"] += 1
                return value, False
        finally:
            self._release_fill_lock(key, fill_lock)

    async def get(self, key: str):
        value = await self._cache.get(key)
        self._stats["hits" if value is not None else "misses"] += 1
        return value

    async def set(self, key: str, value: Any, *, ttl: int | None = None) -> bool:
        stored = await self._cache.set(
            key,
            value,
            expire=self._default_ttl if ttl is None else ttl,
        )
        if stored:
            self._stats["writes"] += 1
        return stored

    async def invalidate_book(self, owner_scope: str, book_id: int) -> int:
        keys = self._book_keys.pop((owner_scope, int(book_id)), OrderedDict())
        for key in keys:
            await self._cache.delete(key)
        return len(keys)

    def _acquire_fill_lock(self, key: str) -> tuple[asyncio.Lock, int]:
        with self._fill_locks_guard:
            current = self._fill_locks.get(key)
            if current is None:
                current = (asyncio.Lock(), 0)
            entry = (current[0], current[1] + 1)
            self._fill_locks[key] = entry
            return entry

    def _release_fill_lock(self, key: str, entry: tuple[asyncio.Lock, int]) -> None:
        with self._fill_locks_guard:
            current = self._fill_locks.get(key)
            if current is None or current[0] is not entry[0]:
                return
            if current[1] <= 1:
                self._fill_locks.pop(key, None)
            else:
                self._fill_locks[key] = (current[0], current[1] - 1)

    async def record_usage(self, *, input_tokens: int = 0, output_tokens: int = 0, cost: float = 0.0) -> None:
        self._stats["input_tokens"] += int(input_tokens)
        self._stats["output_tokens"] += int(output_tokens)
        self._stats["cost"] += float(cost)

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    @staticmethod
    def stable_prefix(*, prompt_version: str, agent_identity: str, toolset_version: str, book_summary: str) -> str:
        return "\n".join(
            [
                f"prompt-version:{prompt_version}",
                f"agent:{agent_identity}",
                f"toolset-version:{toolset_version}",
                "book-summary:",
                book_summary.strip(),
            ]
        )
