"""
NovelRepository 仓储测试

包含两部分：
1. 接口契约测试 - 验证抽象接口定义正确
2. SQLite 集成测试 - 验证 SqliteNovelRepository 实现正确
"""

import pytest
from abc import ABC

from app.domain.repositories.novel_repo import NovelRepository
from app.domain.entities.novel import (
    NovelBook, NovelChapter, NovelEntity, NovelRelationship, NovelEvent, NovelStateChange,
    NovelStatus, EntityType, EventType, StateField, RelationType,
)


class TestNovelRepositoryInterface:
    """接口契约测试"""

    def test_is_abstract(self):
        assert issubclass(NovelRepository, ABC)

    def test_has_required_methods(self):
        required = [
            'save_book', 'get_book_by_id', 'get_book_by_url', 'list_books', 'count_books',
            'update_book_status', 'update_book_summary', 'delete_book',
            'save_chapter', 'save_chapters_batch', 'get_chapter_by_id',
            'get_chapters_by_book', 'count_chapters', 'update_chapter_summary', 'update_chapter_content',
            'save_entity', 'save_entities_batch', 'get_entity_by_id', 'get_entity_by_name',
            'list_entities', 'count_entities', 'get_entity_names_by_book', 'search_entities',
            'save_relationship', 'save_relationships_batch', 'get_relationships_by_book', 'get_relationships_by_entity',
            'save_event', 'save_events_batch', 'get_events',
            'save_state_change', 'save_state_changes_batch', 'get_state_changes',
        ]
        for method in required:
            assert hasattr(NovelRepository, method), f"Missing {method}"


# ========== SQLite 集成测试 ==========

import aiosqlite
from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository


@pytest.fixture
async def repo():
    db = await aiosqlite.connect(":memory:")
    with open("app/database_migrations/novel_schema.sql", encoding="utf-8") as f:
        await db.executescript(f.read())
    repo = SqliteNovelRepository(db)
    yield repo
    await db.close()


class TestSqliteNovelRepository:
    """SQLite 仓储集成测试"""

    async def test_save_and_get_book(self, repo):
        book = NovelBook(book_url="https://test.com", book_name="Test", author="A")
        saved = await repo.save_book(book)
        assert saved.id > 0

        fetched = await repo.get_book(saved.id)
        assert fetched is not None
        assert fetched.book_name == "Test"

    async def test_get_book_by_url(self, repo):
        await repo.save_book(NovelBook(book_url="https://unique.com", book_name="U"))
        fetched = await repo.get_book_by_url("https://unique.com")
        assert fetched is not None
        assert fetched.book_name == "U"

    async def test_list_books_by_status(self, repo):
        await repo.save_book(NovelBook(book_url="https://a.com", status=NovelStatus.READY))
        await repo.save_book(NovelBook(book_url="https://b.com", status=NovelStatus.PENDING))
        results = await repo.list_books(status=NovelStatus.READY)
        assert len(results) == 1
        assert results[0].book_url == "https://a.com"

    async def test_update_book_status(self, repo):
        saved = await repo.save_book(NovelBook(book_url="https://c.com"))
        result = await repo.update_book_status(saved.id, NovelStatus.INGESTING, progress=0.5)
        assert result is True
        fetched = await repo.get_book(saved.id)
        assert fetched.status == NovelStatus.INGESTING
        assert fetched.ingest_progress == 0.5

    async def test_save_and_get_chapter(self, repo):
        book = await repo.save_book(NovelBook(book_url="https://d.com"))
        ch = NovelChapter(book_id=book.id, canonical_full="C1", chapter_title="第一章")
        saved = await repo.save_chapter(ch)
        assert saved.id > 0

        fetched = await repo.get_chapter(saved.id)
        assert fetched.chapter_title == "第一章"

    async def test_save_entities_batch(self, repo):
        book = await repo.save_book(NovelBook(book_url="https://e.com"))
        entities = [
            NovelEntity(book_id=book.id, name="林远", entity_type=EntityType.CHARACTER),
            NovelEntity(book_id=book.id, name="周宁", entity_type=EntityType.CHARACTER),
        ]
        count = await repo.save_entities_batch(entities)
        assert count == 2

        results = await repo.list_entities(book.id)
        assert len(results) == 2

    async def test_search_entities(self, repo):
        book = await repo.save_book(NovelBook(book_url="https://f.com"))
        await repo.save_entity(NovelEntity(book_id=book.id, name="韩立", description="凡人修仙传主角"))
        await repo.save_entity(NovelEntity(book_id=book.id, name="南宫婉", description="韩立的道侣"))

        results = await repo.search_entities(book.id, "韩立")
        assert len(results) == 2  # 名字和描述都匹配

    async def test_save_and_get_relationship(self, repo):
        book = await repo.save_book(NovelBook(book_url="https://g.com"))
        rel = NovelRelationship(
            book_id=book.id, source_entity="林远", target_entity="周宁",
            relation_type=RelationType.ALLY, description="生死之交"
        )
        saved = await repo.save_relationship(rel)
        assert saved.id > 0

        results = await repo.get_relationships(book.id, entity_name="林远")
        assert len(results) == 1
        assert results[0].relation_type == RelationType.ALLY

    async def test_save_and_get_event(self, repo):
        book = await repo.save_book(NovelBook(book_url="https://h.com"))
        event = NovelEvent(
            book_id=book.id, chapter_id=1, chapter_num=1,
            event_type=EventType.BATTLE, description="宗门大比",
            participants=["林远", "周宁"], importance=5
        )
        saved = await repo.save_event(event)
        assert saved.id > 0

        results = await repo.get_events(book.id, min_importance=5)
        assert len(results) == 1
        assert results[0].event_type == EventType.BATTLE

    async def test_save_and_get_state_change(self, repo):
        book = await repo.save_book(NovelBook(book_url="https://i.com"))
        sc = NovelStateChange(
            book_id=book.id, entity_name="林远", chapter_id=1, chapter_num=1,
            field_name=StateField.REALM, before_value="炼气期", after_value="筑基期"
        )
        saved = await repo.save_state_change(sc)
        assert saved.id > 0

        results = await repo.get_state_changes(book.id, entity_name="林远", field_name=StateField.REALM)
        assert len(results) == 1
        assert results[0].before_value == "炼气期"
