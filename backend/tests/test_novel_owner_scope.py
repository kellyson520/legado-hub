import aiosqlite
import pytest

from app.domain.entities.novel import NovelBook, NovelChapter, NovelEntity
from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository
from app.infrastructure.persistence.sqlite.novel_db_migrator import migrate_novel_database


@pytest.fixture
async def owner_scoped_repo():
    db = await aiosqlite.connect(":memory:")
    with open("app/database_migrations/novel_schema.sql", encoding="utf-8") as schema:
        await db.executescript(schema.read())
    try:
        yield SqliteNovelRepository(db)
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_book_chapter_and_knowledge_queries_are_scoped(owner_scoped_repo):
    first = await owner_scoped_repo.save_book(
        "user:1", NovelBook(book_url="https://book.test/1", book_name="甲本")
    )
    second = await owner_scoped_repo.save_book(
        "user:2", NovelBook(book_url="https://book.test/1", book_name="乙本")
    )
    await owner_scoped_repo.save_chapter(
        "user:1",
        NovelChapter(
            book_id=first.id,
            canonical_full="C1",
            canonical_num=1,
            raw_text="甲本正文",
        ),
    )
    await owner_scoped_repo.save_entity(
        "user:1", NovelEntity(book_id=first.id, name="甲人物")
    )

    assert await owner_scoped_repo.get_book_by_id("user:2", first.id) is None
    assert len(await owner_scoped_repo.list_books("user:1")) == 1
    assert len(await owner_scoped_repo.list_books("user:2")) == 1
    assert await owner_scoped_repo.get_chapters_by_book("user:2", first.id) == []
    assert await owner_scoped_repo.search_entities("user:2", first.id, "甲人物") == []
    assert second.owner_scope == "user:2"


@pytest.mark.asyncio
async def test_old_global_url_schema_is_backfilled_and_versioned():
    db = await aiosqlite.connect(":memory:")
    try:
        await db.executescript(
            """CREATE TABLE novels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_url TEXT NOT NULL UNIQUE,
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
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO novels(book_url, book_name) VALUES ('https://legacy.test/book', '旧书');"""
        )

        assert await migrate_novel_database(db) == 1
        async with db.execute("SELECT owner_scope, book_name FROM novels") as cursor:
            assert await cursor.fetchone() == ("legacy", "旧书")

        await db.execute(
            "INSERT INTO novels(book_url, book_name, owner_scope) VALUES (?, ?, ?)",
            ("https://legacy.test/book", "新书甲", "user:1"),
        )
        await db.commit()
        async with db.execute("PRAGMA user_version") as cursor:
            assert (await cursor.fetchone())[0] == 1
    finally:
        await db.close()


def test_model_preference_repository_is_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "preferences.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.domain.entities.novel_runtime import NovelModelPreference
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.novel_model_preference_repo_impl import (
        SQLiteNovelModelPreferenceRepository,
    )

    bootstrap_sqlite()
    repo = SQLiteNovelModelPreferenceRepository()
    repo.save(
        NovelModelPreference(
            owner_scope="user:1",
            scope_type="user",
            scope_id="1",
            task_type="chat",
            model_ref="deepseek-chat",
        )
    )

    assert repo.get("user:1", "user", "1", "chat").model_ref == "deepseek-chat"
    assert repo.get("user:2", "user", "1", "chat") is None
