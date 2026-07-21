from __future__ import annotations

import json
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.dialects.sqlite import insert

from app.domain.repositories.vector_store import VectorRecord, VectorStore
from app.infrastructure.persistence.sqlite.schema import NovelVectorModel


class SQLiteVectorStore(VectorStore):
    """SQLite vector store supporting both aiosqlite tests and app sessions."""

    def __init__(self, db=None, *, session_factory=None):
        if db is None and session_factory is None:
            raise ValueError("SQLiteVectorStore requires a database or session factory")
        self._db = db
        self._session_factory = session_factory

    @property
    def _uses_async_connection(self) -> bool:
        # aiosqlite.Connection exposes row_factory; SQLAlchemy sessions do not.
        return self._db is not None and hasattr(self._db, "row_factory")

    def _open_sync_session(self):
        if self._db is not None:
            return self._db, False
        return self._session_factory(), True

    @staticmethod
    def _schema_sql() -> str:
        return """CREATE TABLE IF NOT EXISTS novel_vectors (
            owner_scope VARCHAR NOT NULL,
            book_id INTEGER NOT NULL,
            chapter_id INTEGER NOT NULL,
            knowledge_version VARCHAR NOT NULL,
            vector TEXT NOT NULL DEFAULT '[]',
            payload TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(owner_scope, book_id, chapter_id, knowledge_version)
        )"""

    async def ensure_collection(self, name: str, dimension: int) -> None:
        del name, dimension  # SQLite uses one fixed local collection.
        if self._uses_async_connection:
            await self._db.execute(self._schema_sql())
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_novel_vectors_scope_book_version "
                "ON novel_vectors(owner_scope, book_id, knowledge_version)"
            )
            await self._db.commit()
            return
        db, owned = self._open_sync_session()
        try:
            db.execute(text(self._schema_sql()))
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_novel_vectors_scope_book_version "
                "ON novel_vectors(owner_scope, book_id, knowledge_version)"
            ))
            db.commit()
        finally:
            if owned:
                db.close()

    async def upsert(self, records: Sequence[VectorRecord]) -> int:
        if not records:
            return 0
        if not self._uses_async_connection:
            db, owned = self._open_sync_session()
            try:
                values = [
                    {
                        "owner_scope": record.owner_scope,
                        "book_id": record.book_id,
                        "chapter_id": record.chapter_id,
                        "knowledge_version": record.knowledge_version,
                        "vector": json.dumps(record.vector),
                        "payload": json.dumps(record.payload, ensure_ascii=False),
                    }
                    for record in records
                ]
                statement = insert(NovelVectorModel).values(values)
                db.execute(
                    statement.on_conflict_do_update(
                        index_elements=[
                            NovelVectorModel.owner_scope,
                            NovelVectorModel.book_id,
                            NovelVectorModel.chapter_id,
                            NovelVectorModel.knowledge_version,
                        ],
                        set_={
                            "vector": statement.excluded.vector,
                            "payload": statement.excluded.payload,
                        },
                    )
                )
                db.commit()
                return len(records)
            finally:
                if owned:
                    db.close()
        for record in records:
            await self._db.execute(
                """INSERT INTO novel_vectors (
                    owner_scope, book_id, chapter_id, knowledge_version, vector, payload
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_scope, book_id, chapter_id, knowledge_version) DO UPDATE SET
                    vector=excluded.vector, payload=excluded.payload""",
                (
                    record.owner_scope,
                    record.book_id,
                    record.chapter_id,
                    record.knowledge_version,
                    json.dumps(record.vector),
                    json.dumps(record.payload, ensure_ascii=False),
                ),
            )
        await self._db.commit()
        return len(records)

    async def search(self, owner_scope: str, book_id: int, knowledge_version: str, query_vector: list[float], top_k: int) -> list[VectorRecord]:
        if not self._uses_async_connection:
            db, owned = self._open_sync_session()
            try:
                rows = (
                    db.query(NovelVectorModel)
                    .filter(
                        NovelVectorModel.owner_scope == owner_scope,
                        NovelVectorModel.book_id == book_id,
                        NovelVectorModel.knowledge_version == knowledge_version,
                    )
                    .all()
                )
                results = [
                    VectorRecord(
                        row.owner_scope,
                        row.book_id,
                        row.chapter_id,
                        row.knowledge_version,
                        json.loads(row.vector),
                        json.loads(row.payload),
                        _cosine(query_vector, json.loads(row.vector)),
                    )
                    for row in rows
                ]
                results.sort(key=lambda item: item.score, reverse=True)
                return results[: max(0, int(top_k))]
            finally:
                if owned:
                    db.close()
        async with self._db.execute(
            """SELECT owner_scope, book_id, chapter_id, knowledge_version, vector, payload
               FROM novel_vectors WHERE owner_scope=? AND book_id=? AND knowledge_version=?""",
            (owner_scope, book_id, knowledge_version),
        ) as cursor:
            rows = await cursor.fetchall()
        results = []
        for row in rows:
            vector = json.loads(row[4])
            score = _cosine(query_vector, vector)
            results.append(VectorRecord(row[0], row[1], row[2], row[3], vector, json.loads(row[5]), score))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[: max(0, int(top_k))]

    async def delete_book(self, owner_scope: str, book_id: int, knowledge_version: str | None = None) -> int:
        if not self._uses_async_connection:
            db, owned = self._open_sync_session()
            try:
                query = db.query(NovelVectorModel).filter(
                    NovelVectorModel.owner_scope == owner_scope,
                    NovelVectorModel.book_id == book_id,
                )
                if knowledge_version is not None:
                    query = query.filter(NovelVectorModel.knowledge_version == knowledge_version)
                count = query.delete(synchronize_session=False)
                db.commit()
                return int(count or 0)
            finally:
                if owned:
                    db.close()
        if knowledge_version is None:
            cursor = await self._db.execute(
                "DELETE FROM novel_vectors WHERE owner_scope=? AND book_id=?",
                (owner_scope, book_id),
            )
        else:
            cursor = await self._db.execute(
                "DELETE FROM novel_vectors WHERE owner_scope=? AND book_id=? AND knowledge_version=?",
                (owner_scope, book_id, knowledge_version),
            )
        await self._db.commit()
        return cursor.rowcount

    async def health(self) -> dict[str, Any]:
        try:
            if self._uses_async_connection:
                await self._db.execute("SELECT 1")
            else:
                db, owned = self._open_sync_session()
                try:
                    db.execute(text("SELECT 1"))
                finally:
                    if owned:
                        db.close()
            return {"enabled": True, "backend": "sqlite"}
        except Exception as exc:
            return {"enabled": False, "backend": "sqlite", "error": str(exc)[:200]}


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
