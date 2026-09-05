"""Application-level cache provider contract."""

from __future__ import annotations

from typing import Any, Protocol


class CacheProvider(Protocol):
    async def get(self, key: str) -> Any | None:
        ...

    async def set(self, key: str, value: Any, expire: int = 3600) -> bool:
        ...

    async def delete(self, key: str) -> bool:
        ...

    async def exists(self, key: str) -> bool:
        ...

    async def increment(self, key: str, amount: int = 1, expire: int = 86400) -> int:
        ...

    async def get_counter(self, key: str) -> int:
        ...

    async def reset_counter(self, key: str) -> bool:
        ...
