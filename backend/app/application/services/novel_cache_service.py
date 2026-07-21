from __future__ import annotations

import inspect
import json
from collections import defaultdict
from hashlib import sha256
from typing import Any, Awaitable, Callable

from app.infrastructure.cache.abstract import CacheProvider


class NovelCacheService:
    """Owner-aware cache facade with deterministic invalidation and metrics."""

    def __init__(self, cache: CacheProvider, *, default_ttl: int = 3600):
        self._cache = cache
        self._default_ttl = default_ttl
        self._book_keys: dict[tuple[str, int], set[str]] = defaultdict(set)
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
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        key = "novel:v1:" + sha256(payload.encode("utf-8")).hexdigest()
        if book_id is not None:
            self._book_keys[(owner_scope, int(book_id))].add(key)
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

    async def invalidate_book(self, owner_scope: str, book_id: int) -> int:
        keys = self._book_keys.pop((owner_scope, int(book_id)), set())
        for key in keys:
            await self._cache.delete(key)
        return len(keys)

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
