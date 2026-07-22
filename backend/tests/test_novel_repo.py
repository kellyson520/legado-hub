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
from app.domain.entities.novel_runtime import NovelIndexState


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

    async def test_evidence_round_trips_for_relationship_event_and_state_change(self, repo):
        book = await repo.save_book(
            "user:1",
            NovelBook(book_url="https://evidence.test", book_name="证据书", owner_scope="user:1"),
        )
        evidence = [{"chapter_id": 0, "start_offset": 2, "end_offset": 12, "text": "正文证据"}]
        relationship = NovelRelationship(
            book_id=book.id,
            source_entity="江轩",
            target_entity="周宁",
            relation_type=RelationType.ALLY,
            description="并肩作战",
            evidence=evidence,
        )
        event = NovelEvent(
            book_id=book.id,
            chapter_id=0,
            chapter_num=0,
            event_type=EventType.BATTLE,
            description="并肩作战",
            participants=["江轩", "周宁"],
            evidence=evidence,
        )
        state = NovelStateChange(
            book_id=book.id,
            entity_name="玄天剑",
            chapter_id=0,
            chapter_num=0,
            field_name=StateField.POSSESSION,
            before_value="",
            after_value="江轩",
            trigger_event="获得",
            evidence=evidence,
        )
        await repo.save_relationship("user:1", relationship)
        await repo.save_event("user:1", event)
        await repo.save_state_change("user:1", state)

        assert (await repo.get_relationships("user:1", book.id, limit=10))[0].evidence == evidence
        assert (await repo.get_events("user:1", book.id, limit=10))[0].evidence == evidence
        assert (await repo.get_state_changes("user:1", book.id, limit=10))[0].evidence == evidence

    async def test_rebuilding_book_knowledge_from_snapshots_updates_counts(self, repo):
        book = await repo.save_book(
            "user:1",
            NovelBook(book_url="https://snapshot.test", book_name="快照书", owner_scope="user:1"),
        )
        first = {
            "chapter_id": 1,
            "chapter_num": 1,
            "entities": [{"name": "江轩", "entity_type": "character", "appearance_count": 2}],
            "relationships": [],
            "events": [],
            "state_changes": [],
        }
        second = {
            "chapter_id": 2,
            "chapter_num": 2,
            "entities": [{"name": "玄天剑", "entity_type": "item", "appearance_count": 1}],
            "relationships": [],
            "events": [],
            "state_changes": [],
        }

        await repo.replace_book_knowledge("user:1", book.id, [first, second])
        initial = await repo.get_book_by_id("user:1", book.id)
        assert initial.character_count == 1
        assert initial.entity_count == 2

        await repo.replace_book_knowledge("user:1", book.id, [second])
        updated = await repo.get_book_by_id("user:1", book.id)
        assert updated.character_count == 0
        assert updated.entity_count == 1

    async def test_index_snapshot_payload_round_trips_and_lists_by_book(self, repo):
        book = await repo.save_book(
            "user:1",
            NovelBook(book_url="https://index-state.test", book_name="索引书", owner_scope="user:1"),
        )
        state = NovelIndexState(
            owner_scope="user:1",
            book_id=book.id,
            chapter_id=0,
            content_hash="hash-0",
            knowledge_version="v2-local-evidence",
            extraction_status="completed",
            extraction_payload={"entities": [{"name": "江轩"}], "relationships": []},
        )

        await repo.save_index_state(state)

        fetched = await repo.get_index_state("user:1", book.id, chapter_id=0)
        assert fetched is not None
        assert fetched.extraction_payload == state.extraction_payload
        states = await repo.list_index_states("user:1", book.id)
        assert len(states) == 1
        assert states[0].chapter_id == 0
        assert await repo.list_index_states("user:2", book.id) == []
