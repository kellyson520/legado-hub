from __future__ import annotations

from typing import Any, Sequence

from app.domain.repositories.vector_store import VectorRecord, VectorStore, VectorStoreUnavailable


class PgVectorStore(VectorStore):
    def __init__(self, session=None, *, session_factory=None, table: str = "novel_vectors"):
        self._session = session
        self._session_factory = session_factory
        self._table = table

    def _require_session(self):
        if self._session is None and self._session_factory is None:
            raise VectorStoreUnavailable("pgvector session/driver is not configured")
        return self._session or self._session_factory()

    async def ensure_collection(self, name: str, dimension: int) -> None:
        self._require_session()
        raise VectorStoreUnavailable("pgvector adapter requires an explicit SQLAlchemy vector extension")

    async def upsert(self, records: Sequence[VectorRecord]) -> int:
        self._require_session()
        raise VectorStoreUnavailable("pgvector adapter requires an explicit SQLAlchemy vector extension")

    async def search(self, owner_scope: str, book_id: int, knowledge_version: str, query_vector: list[float], top_k: int) -> list[VectorRecord]:
        self._require_session()
        raise VectorStoreUnavailable("pgvector adapter requires an explicit SQLAlchemy vector extension")

    async def delete_book(self, owner_scope: str, book_id: int, knowledge_version: str | None = None) -> int:
        self._require_session()
        raise VectorStoreUnavailable("pgvector adapter requires an explicit SQLAlchemy vector extension")

    async def health(self) -> dict[str, Any]:
        if self._session is None and self._session_factory is None:
            return {"enabled": False, "backend": "pgvector", "reason": "driver unavailable"}
        return {"enabled": False, "backend": "pgvector", "reason": "extension check required"}
