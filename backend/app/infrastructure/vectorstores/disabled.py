from typing import Any, Sequence

from app.domain.repositories.vector_store import VectorRecord, VectorStore


class DisabledVectorStore(VectorStore):
    async def ensure_collection(self, name: str, dimension: int) -> None:
        return None

    async def upsert(self, records: Sequence[VectorRecord]) -> int:
        return 0

    async def search(self, owner_scope: str, book_id: int, knowledge_version: str, query_vector: list[float], top_k: int) -> list[VectorRecord]:
        return []

    async def delete_book(self, owner_scope: str, book_id: int, knowledge_version: str | None = None) -> int:
        return 0

    async def health(self) -> dict[str, Any]:
        return {"enabled": False, "backend": "disabled", "reason": "vector store disabled"}
