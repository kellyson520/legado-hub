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
            record_key VARCHAR NOT NULL DEFAULT '',
            vector TEXT NOT NULL DEFAULT '[]',
            payload TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(owner_scope, book_id, knowledge_version, record_key)
        )"""

    @staticmethod
    def _record_key(record: VectorRecord) -> str:
        return record.record_key or f"chapter:{int(record.chapter_id)}"

    @classmethod
    def _payload(cls, record: VectorRecord, record_key: str) -> dict[str, Any]:
        payload = dict(record.payload or {})
        payload.setdefault("record_key", record_key)
        return payload

    async def _ensure_async_schema(self) -> None:
        async with self._db.execute("PRAGMA table_info(novel_vectors)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if not columns:
            await self._db.execute(self._schema_sql())
        elif "record_key" not in columns:
            await self._db.execute("ALTER TABLE novel_vectors RENAME TO novel_vectors_legacy")
            await self._db.execute(self._schema_sql())
            await self._db.execute(
                """INSERT INTO novel_vectors (
                   owner_scope, book_id, chapter_id, knowledge_version,
                   record_key, vector, payload
                ) SELECT owner_scope, book_id, chapter_id, knowledge_version,
                   'chapter:' || CAST(chapter_id AS TEXT), vector, payload
                   FROM novel_vectors_legacy"""
            )
            await self._db.execute("DROP TABLE novel_vectors_legacy")
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_novel_vectors_scope_book_version "
            "ON novel_vectors(owner_scope, book_id, knowledge_version)"
        )
        await self._db.commit()

    def _ensure_sync_schema(self, db) -> None:
        columns = {row[1] for row in db.execute(text("PRAGMA table_info(novel_vectors)")).fetchall()}
        if not columns:
            db.execute(text(self._schema_sql()))
        elif "record_key" not in columns:
            db.execute(text("ALTER TABLE novel_vectors RENAME TO novel_vectors_legacy"))
            db.execute(text(self._schema_sql()))
            db.execute(text(
                """INSERT INTO novel_vectors (
                   owner_scope, book_id, chapter_id, knowledge_version,
                   record_key, vector, payload
                ) SELECT owner_scope, book_id, chapter_id, knowledge_version,
                   'chapter:' || CAST(chapter_id AS TEXT), vector, payload
                   FROM novel_vectors_legacy"""
            ))
            db.execute(text("DROP TABLE novel_vectors_legacy"))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_novel_vectors_scope_book_version "
            "ON novel_vectors(owner_scope, book_id, knowledge_version)"
        ))

    async def ensure_collection(self, name: str, dimension: int) -> None:
        del name, dimension  # SQLite uses one fixed local collection.
        if self._uses_async_connection:
            await self._ensure_async_schema()
            return
        db, owned = self._open_sync_session()
        try:
            self._ensure_sync_schema(db)
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
                self._ensure_sync_schema(db)
                values = [
                    {
                        "owner_scope": record.owner_scope,
                        "book_id": record.book_id,
                        "chapter_id": record.chapter_id,
                        "knowledge_version": record.knowledge_version,
                        "record_key": self._record_key(record),
                        "vector": json.dumps(record.vector),
                        "payload": json.dumps(
                            self._payload(record, self._record_key(record)), ensure_ascii=False
                        ),
                    }
                    for record in records
                ]
                statement = insert(NovelVectorModel).values(values)
                db.execute(
                    statement.on_conflict_do_update(
                        index_elements=[
                            NovelVectorModel.owner_scope,
                            NovelVectorModel.book_id,
                            NovelVectorModel.knowledge_version,
                            NovelVectorModel.record_key,
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
        await self._ensure_async_schema()
        for record in records:
            record_key = self._record_key(record)
            await self._db.execute(
                """INSERT INTO novel_vectors (
                    owner_scope, book_id, chapter_id, knowledge_version, record_key, vector, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_scope, book_id, knowledge_version, record_key) DO UPDATE SET
                    vector=excluded.vector, payload=excluded.payload""",
                (
                    record.owner_scope,
                    record.book_id,
                    record.chapter_id,
                    record.knowledge_version,
                    record_key,
                    json.dumps(record.vector),
                    json.dumps(self._payload(record, record_key), ensure_ascii=False),
                ),
            )
        await self._db.commit()
        return len(records)

    async def search(self, owner_scope: str, book_id: int, knowledge_version: str, query_vector: list[float], top_k: int) -> list[VectorRecord]:
        if self._uses_async_connection:
            await self._ensure_async_schema()
        if not self._uses_async_connection:
            db, owned = self._open_sync_session()
            try:
                self._ensure_sync_schema(db)
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
                        _payload_with_record_key(json.loads(row.payload), row.record_key, row.chapter_id),
                        _cosine(query_vector, json.loads(row.vector)),
                        row.record_key,
                    )
                    for row in rows
                ]
                results.sort(key=lambda item: item.score, reverse=True)
                return results[: max(0, int(top_k))]
            finally:
                if owned:
                    db.close()
        async with self._db.execute(
            """SELECT owner_scope, book_id, chapter_id, knowledge_version, record_key, vector, payload
               FROM novel_vectors WHERE owner_scope=? AND book_id=? AND knowledge_version=?""",
            (owner_scope, book_id, knowledge_version),
        ) as cursor:
            rows = await cursor.fetchall()
        results = []
        for row in rows:
            vector = json.loads(row[5])
            score = _cosine(query_vector, vector)
            payload = _payload_with_record_key(json.loads(row[6]), row[4], row[2])
            results.append(
                VectorRecord(
                    row[0], row[1], row[2], row[3], vector, payload, score,
                    row[4] or payload.get("record_key") or f"chapter:{row[2]}",
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return results[: max(0, int(top_k))]

    async def delete_book(self, owner_scope: str, book_id: int, knowledge_version: str | None = None) -> int:
        if not self._uses_async_connection:
            db, owned = self._open_sync_session()
            try:
                self._ensure_sync_schema(db)
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
        await self._ensure_async_schema()
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


def _payload_with_record_key(payload: dict[str, Any], record_key: str, chapter_id: int) -> dict[str, Any]:
    payload = dict(payload or {})
    payload.setdefault("record_key", record_key or f"chapter:{int(chapter_id)}")
    return payload
