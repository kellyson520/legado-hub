"""
NovelIngestionService 集成测试
"""

import pytest
import aiosqlite

from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository
from app.application.services.novel_ingestion_service import NovelIngestionService
from app.domain.services.chapter_mapper import ChapterCanonicalMapper
from app.domain.entities.novel import NovelStatus


@pytest.fixture
async def ingestion_service():
    db = await aiosqlite.connect(":memory:")
    with open("app/database_migrations/novel_schema.sql", encoding="utf-8") as f:
        await db.executescript(f.read())
    repo = SqliteNovelRepository(db)
    service = NovelIngestionService(repo)
    yield service
    await db.close()


def test_chapter_mapper_keeps_repeated_volume_numbers_unique():
    mapped = ChapterCanonicalMapper.map_batch(
        ["第1章 第一卷", "第2章 第一卷", "第1章 第二卷", "第2章 第二卷"]
    )
    assert len({chapter.canonical_full for chapter in mapped}) == 4


class TestNovelIngestionService:
    """摄入服务集成测试"""

    async def test_ingest_new_book(self, ingestion_service):
        titles = [f"第{i}章 标题{i}" for i in range(1, 11)]
        book = await ingestion_service.ingest_catalog(
            book_url="https://test.com/book/1",
            book_name="测试书籍",
            raw_titles=titles,
            author="测试作者",
            source_name="测试源",
        )
        assert book.id > 0
        assert book.book_name == "测试书籍"
        assert book.total_chapters == 10
        assert book.status == NovelStatus.SUMMARIZING

    async def test_ingest_idempotent(self, ingestion_service):
        titles = ["第1章 A", "第2章 B"]
        book1 = await ingestion_service.ingest_catalog(
            book_url="https://idempotent.com",
            book_name="重复测试",
            raw_titles=titles,
        )
        book2 = await ingestion_service.ingest_catalog(
            book_url="https://idempotent.com",
            book_name="重复测试",
            raw_titles=titles,
        )
        assert book1.id == book2.id

    async def test_ingest_catalog_isolated_by_owner_scope(self, ingestion_service):
        first = await ingestion_service.ingest_catalog(
            book_url="https://scoped.test/book",
            book_name="甲本",
            raw_titles=["第1章 甲"],
            owner_scope="user:1",
        )
        second = await ingestion_service.ingest_catalog(
            book_url="https://scoped.test/book",
            book_name="乙本",
            raw_titles=["第1章 乙"],
            owner_scope="user:2",
        )

        assert first.id != second.id
        assert first.owner_scope == "user:1"
        assert second.owner_scope == "user:2"

    async def test_save_progress_persists_all_reader_preferences(self, ingestion_service):
        book = await ingestion_service.ingest_catalog(
            book_url="https://reader.test/book",
            book_name="阅读设置",
            raw_titles=["第1章 开始"],
            owner_scope="user:1",
        )
        chapter = (await ingestion_service._repo.get_chapters_by_book("user:1", book.id))[0]

        progress = await ingestion_service.save_progress(
            "user:1",
            book.id,
            chapter.id,
            120,
            0.6,
            {"theme": "night", "background": "#101010", "fontSize": 22, "lineHeight": 2.1, "contentWidth": "compact"},
        )

        assert progress["font_size"] == 22
        assert progress["line_height"] == 2.1
        assert progress["content_width"] == "compact"
