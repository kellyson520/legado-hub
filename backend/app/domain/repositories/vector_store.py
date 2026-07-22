from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class VectorRecord:
    owner_scope: str
    book_id: int
    chapter_id: int
    knowledge_version: str
    vector: list[float]
    payload: dict[str, Any]
    score: float = 0.0
    record_key: str = ""


class VectorStoreUnavailable(RuntimeError):
    code = "vector_store_unavailable"


class VectorStore(ABC):
    @abstractmethod
    async def ensure_collection(self, name: str, dimension: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def upsert(self, records: Sequence[VectorRecord]) -> int:
        raise NotImplementedError

    @abstractmethod
    async def search(
        self,
        owner_scope: str,
        book_id: int,
        knowledge_version: str,
        query_vector: list[float],
        top_k: int,
    ) -> list[VectorRecord]:
        raise NotImplementedError

    @abstractmethod
    async def delete_book(self, owner_scope: str, book_id: int, knowledge_version: str | None = None) -> int:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        raise NotImplementedError
