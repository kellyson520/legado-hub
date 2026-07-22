"""Recoverable migrations for the standalone ``novel.db`` SQLite store."""

from __future__ import annotations

import re
from typing import Any


NOVEL_COLUMNS = (
    "id", "book_url", "book_name", "author", "source_name", "total_chapters",
    "total_words", "status", "source_type", "ingest_progress", "ingest_error_msg",
    "character_count", "entity_count", "event_count", "relationship_count",
    "summary_global", "created_at", "updated_at",
)


async def migrate_novel_database(db: Any) -> int:
    """Migrate an old global-URL schema without exposing partial state.

    The function is deliberately independent of the application settings so it
    can be used by startup code and by migration tests with an in-memory DB.
    ``user_version`` is advanced only after all DDL and data copy operations
    have committed successfully.
    """

    await db.execute("PRAGMA foreign_keys=OFF")
    # SQLite normally rewrites dependent foreign keys when a table is
    # temporarily renamed.  That would leave them pointing at
    # ``novels_legacy`` after the copy completes.
    await db.execute("PRAGMA legacy_alter_table=ON")
    await _repair_legacy_foreign_keys(db)
    async with db.execute("PRAGMA user_version") as cursor:
        current_version = int((await cursor.fetchone())[0])

    async with db.execute("PRAGMA table_info(novels)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}

    if columns and "owner_scope" not in columns:
        await db.execute("ALTER TABLE novels RENAME TO novels_legacy")
        await db.execute(
            """CREATE TABLE novels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_url TEXT NOT NULL,
                book_name TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                source_name TEXT NOT NULL DEFAULT '',
                total_chapters INTEGER NOT NULL DEFAULT 0,
                total_words INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                source_type TEXT NOT NULL DEFAULT 'book_source',
                ingest_progress REAL NOT NULL DEFAULT 0.0,
                ingest_error_msg TEXT,
                character_count INTEGER NOT NULL DEFAULT 0,
                entity_count INTEGER NOT NULL DEFAULT 0,
                event_count INTEGER NOT NULL DEFAULT 0,
                relationship_count INTEGER NOT NULL DEFAULT 0,
                summary_global TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                owner_scope TEXT NOT NULL DEFAULT 'legacy'
            )"""
        )
        selected = ", ".join(NOVEL_COLUMNS)
        await db.execute(
            f"INSERT INTO novels ({selected}, owner_scope) "
            f"SELECT {selected}, 'legacy' FROM novels_legacy"
        )
        await db.execute("DROP TABLE novels_legacy")

    await db.executescript(
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_novels_owner_url
               ON novels(owner_scope, book_url);
           CREATE INDEX IF NOT EXISTS idx_novels_status ON novels(status);
           CREATE INDEX IF NOT EXISTS idx_novels_owner_updated
               ON novels(owner_scope, updated_at DESC);
           CREATE TABLE IF NOT EXISTS novel_index_states (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               owner_scope TEXT NOT NULL,
               book_id INTEGER NOT NULL,
               chapter_id INTEGER,
               content_hash TEXT NOT NULL DEFAULT '',
               knowledge_version TEXT NOT NULL DEFAULT '',
               extraction_status TEXT NOT NULL DEFAULT 'pending',
               bm25_status TEXT NOT NULL DEFAULT 'pending',
               vector_status TEXT NOT NULL DEFAULT 'disabled',
               embedding_model TEXT NOT NULL DEFAULT '',
               embedding_dimension INTEGER NOT NULL DEFAULT 0,
               last_success_at TIMESTAMP,
               failure_reason TEXT NOT NULL DEFAULT '',
               updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               FOREIGN KEY(book_id) REFERENCES novels(id) ON DELETE CASCADE
           );
           CREATE INDEX IF NOT EXISTS idx_novel_index_states_owner_book
               ON novel_index_states(owner_scope, book_id, chapter_id);
           CREATE TABLE IF NOT EXISTS novel_adjudication_candidates (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               owner_scope TEXT NOT NULL,
               book_id INTEGER NOT NULL,
               chapter_id INTEGER,
               candidate_key TEXT NOT NULL,
               content_hash TEXT NOT NULL DEFAULT '',
               candidate_payload TEXT NOT NULL DEFAULT '{}',
               evidence_payload TEXT NOT NULL DEFAULT '[]',
               status TEXT NOT NULL DEFAULT 'pending',
               decision_payload TEXT NOT NULL DEFAULT '{}',
               attempts INTEGER NOT NULL DEFAULT 0,
               created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               FOREIGN KEY(book_id) REFERENCES novels(id) ON DELETE CASCADE,
               UNIQUE(owner_scope, book_id, chapter_id, candidate_key)
           );
           CREATE INDEX IF NOT EXISTS idx_novel_adjudication_scope_status
               ON novel_adjudication_candidates(owner_scope, book_id, status, updated_at DESC);
           CREATE TABLE IF NOT EXISTS evolution_feedbacks (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               book_id INTEGER NOT NULL,
               feedback_type TEXT NOT NULL,
               target_type TEXT NOT NULL,
               target_id INTEGER NOT NULL,
               original_value TEXT NOT NULL DEFAULT '',
               corrected_value TEXT NOT NULL DEFAULT '',
               reason TEXT NOT NULL DEFAULT '',
               user_id INTEGER,
               confidence REAL NOT NULL DEFAULT 1.0,
               applied BOOLEAN NOT NULL DEFAULT 0,
               created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
           );
           CREATE INDEX IF NOT EXISTS idx_feedback_book ON evolution_feedbacks(book_id, target_type);
           CREATE TABLE IF NOT EXISTS evolution_rules (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               book_id INTEGER NOT NULL DEFAULT 0,
               rule_type TEXT NOT NULL,
               pattern TEXT NOT NULL,
               replacement TEXT NOT NULL DEFAULT '',
               condition TEXT NOT NULL DEFAULT '{}',
               hit_count INTEGER NOT NULL DEFAULT 0,
               success_count INTEGER NOT NULL DEFAULT 0,
               failure_count INTEGER NOT NULL DEFAULT 0,
               active BOOLEAN NOT NULL DEFAULT 1,
               created_from_feedback_id INTEGER,
               created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
           );
           CREATE INDEX IF NOT EXISTS idx_rules_book ON evolution_rules(book_id, rule_type, active);
           CREATE TABLE IF NOT EXISTS novel_reading_progress (
               owner_scope TEXT NOT NULL,
               book_id INTEGER NOT NULL,
               chapter_id INTEGER NOT NULL,
               offset_chars INTEGER NOT NULL DEFAULT 0,
               percent REAL NOT NULL DEFAULT 0.0,
               theme TEXT NOT NULL DEFAULT 'paper',
               background TEXT NOT NULL DEFAULT '',
               font_size INTEGER NOT NULL DEFAULT 18,
               updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               PRIMARY KEY(owner_scope, book_id),
               FOREIGN KEY(book_id) REFERENCES novels(id) ON DELETE CASCADE
           );
           CREATE TABLE IF NOT EXISTS novel_model_preferences (
               owner_scope TEXT NOT NULL,
               scope_type TEXT NOT NULL,
               scope_id TEXT NOT NULL,
               task_type TEXT NOT NULL,
               model_ref TEXT NOT NULL,
               provider_group TEXT NOT NULL DEFAULT 'novel',
               updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               PRIMARY KEY(owner_scope, scope_type, scope_id, task_type)
           );"""
    )
    for table, column, definition in (
        ("novel_index_states", "extraction_payload", "TEXT NOT NULL DEFAULT '{}'"),
        ("novel_relationships", "evidence", "TEXT NOT NULL DEFAULT '[]'"),
        ("novel_events", "evidence", "TEXT NOT NULL DEFAULT '[]'"),
        ("novel_state_changes", "evidence", "TEXT NOT NULL DEFAULT '[]'"),
    ):
        async with db.execute(f"PRAGMA table_info({table})") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if columns and column not in columns:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    async with db.execute("PRAGMA table_info(novel_reading_progress)") as cursor:
        progress_columns = {row[1] for row in await cursor.fetchall()}
    if progress_columns:
        if "line_height" not in progress_columns:
            await db.execute("ALTER TABLE novel_reading_progress ADD COLUMN line_height REAL NOT NULL DEFAULT 1.9")
        if "content_width" not in progress_columns:
            await db.execute("ALTER TABLE novel_reading_progress ADD COLUMN content_width TEXT NOT NULL DEFAULT 'comfortable'")
    await _ensure_keyed_vector_table(db)
    await db.commit()
    if current_version < 1:
        await db.execute("PRAGMA user_version=1")
        await db.commit()
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA legacy_alter_table=OFF")
    return max(current_version, 1)


async def _ensure_keyed_vector_table(db: Any) -> None:
    """Upgrade chapter-only vectors so one chapter can hold many memories."""
    async with db.execute("PRAGMA table_info(novel_vectors)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}
    if columns and "record_key" not in columns:
        await db.execute("ALTER TABLE novel_vectors RENAME TO novel_vectors_legacy")
        columns = set()
    if not columns:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS novel_vectors (
               owner_scope TEXT NOT NULL,
               book_id INTEGER NOT NULL,
               chapter_id INTEGER NOT NULL,
               knowledge_version TEXT NOT NULL,
               record_key TEXT NOT NULL DEFAULT '',
               vector TEXT NOT NULL DEFAULT '[]',
               payload TEXT NOT NULL DEFAULT '{}',
               PRIMARY KEY(owner_scope, book_id, knowledge_version, record_key),
               FOREIGN KEY(book_id) REFERENCES novels(id) ON DELETE CASCADE
            )"""
        )
        async with db.execute("PRAGMA table_info(novel_vectors_legacy)") as cursor:
            legacy_columns = {row[1] for row in await cursor.fetchall()}
        if legacy_columns:
            await db.execute(
                """INSERT INTO novel_vectors (
                   owner_scope, book_id, chapter_id, knowledge_version,
                   record_key, vector, payload
                ) SELECT owner_scope, book_id, chapter_id, knowledge_version,
                   'chapter:' || CAST(chapter_id AS TEXT), vector, payload
                   FROM novel_vectors_legacy"""
            )
            await db.execute("DROP TABLE novel_vectors_legacy")
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_novel_vectors_scope_book_version "
        "ON novel_vectors(owner_scope, book_id, knowledge_version)"
    )


async def _repair_legacy_foreign_keys(db: Any) -> None:
    """Repair databases created by the pre-owner-scope rename migration."""
    async with db.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ) as cursor:
        tables = await cursor.fetchall()

    for table_name, create_sql in tables:
        if not create_sql or "novels_legacy" not in create_sql:
            continue
        table = str(table_name)
        backup = f"__novel_fk_repair_{table}"
        quoted_table = '"' + table.replace('"', '""') + '"'
        quoted_backup = '"' + backup.replace('"', '""') + '"'
        await db.execute(f"ALTER TABLE {quoted_table} RENAME TO {quoted_backup}")
        repaired_sql = create_sql.replace("novels_legacy", "novels")
        repaired_sql = re.sub(
            rf"(?i)(CREATE TABLE(?: IF NOT EXISTS)?\s+)(?:\"?{re.escape(table)}\"?)",
            rf'\1"{table}"',
            repaired_sql,
            count=1,
        )
        await db.execute(repaired_sql)
        async with db.execute(f"PRAGMA table_info({quoted_backup})") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
        if columns:
            column_sql = ", ".join('"' + str(column).replace('"', '""') + '"' for column in columns)
            await db.execute(
                f"INSERT INTO {quoted_table} ({column_sql}) SELECT {column_sql} FROM {quoted_backup}"
            )
        await db.execute(f"DROP TABLE {quoted_backup}")
    await db.commit()
