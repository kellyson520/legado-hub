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
            'upsert_adjudication_candidate', 'list_adjudication_candidates', 'update_adjudication_candidate',
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

    async def test_get_chapters_by_book_includes_zero_number_chapters_by_default(self, repo):
        book = await repo.save_book(
            "user:1", NovelBook(book_url="https://chapter-zero.test", owner_scope="user:1")
        )
        await repo.save_chapter(
            "user:1",
            NovelChapter(book_id=book.id, canonical_full="P0", canonical_num=0, chapter_title="序章"),
        )

        chapters = await repo.get_chapters_by_book("user:1", book.id)

        assert [chapter.canonical_num for chapter in chapters] == [0]

    async def test_legacy_evidence_column_order_is_read_by_name(self):
        """Evidence added by ALTER TABLE must not be decoded by SELECT * offsets."""
        import aiosqlite

        db = await aiosqlite.connect(":memory:")
        try:
            with open("app/database_migrations/novel_schema.sql", encoding="utf-8") as schema:
                await db.executescript(schema.read())
            book = await self._save_book_for_repo(db, "https://legacy-evidence.test")
            await db.execute("DROP TABLE novel_relationships")
            await db.execute(
                """CREATE TABLE novel_relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    source_entity TEXT NOT NULL,
                    target_entity TEXT NOT NULL,
                    relation_type TEXT NOT NULL DEFAULT 'custom',
                    description TEXT NOT NULL DEFAULT '',
                    since_chapter INTEGER NOT NULL DEFAULT 0,
                    until_chapter INTEGER,
                    confidence REAL NOT NULL DEFAULT 0.8,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    evidence TEXT NOT NULL DEFAULT '[]'
                )"""
            )
            await db.execute(
                """INSERT INTO novel_relationships (
                    book_id, source_entity, target_entity, relation_type, description,
                    since_chapter, confidence, evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (book.id, "江轩", "周宁", "ally", "并肩作战", 0, 0.9, '[{"text":"旧库证据"}]'),
            )
            await db.execute("DROP TABLE novel_events")
            await db.execute(
                """CREATE TABLE novel_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    chapter_id INTEGER NOT NULL,
                    chapter_num INTEGER NOT NULL,
                    event_type TEXT NOT NULL DEFAULT 'custom',
                    description TEXT NOT NULL DEFAULT '',
                    participants TEXT NOT NULL DEFAULT '[]',
                    location TEXT NOT NULL DEFAULT '',
                    importance INTEGER NOT NULL DEFAULT 3,
                    related_entities TEXT NOT NULL DEFAULT '[]',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    evidence TEXT NOT NULL DEFAULT '[]'
                )"""
            )
            await db.execute(
                """INSERT INTO novel_events (
                    book_id, chapter_id, chapter_num, event_type, description,
                    participants, location, importance, related_entities, evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (book.id, 0, 0, "battle", "旧事件", "[]", "", 3, "[]", '[{"text":"旧事件证据"}]'),
            )
            await db.execute("DROP TABLE novel_state_changes")
            await db.execute(
                """CREATE TABLE novel_state_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    entity_name TEXT NOT NULL,
                    chapter_id INTEGER NOT NULL,
                    chapter_num INTEGER NOT NULL,
                    field_name TEXT NOT NULL DEFAULT 'custom',
                    before_value TEXT NOT NULL DEFAULT '',
                    after_value TEXT NOT NULL DEFAULT '',
                    trigger_event TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.8,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    evidence TEXT NOT NULL DEFAULT '[]'
                )"""
            )
            await db.execute(
                """INSERT INTO novel_state_changes (
                    book_id, entity_name, chapter_id, chapter_num, field_name,
                    before_value, after_value, trigger_event, confidence, evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (book.id, "玄天剑", 0, 0, "possession", "", "江轩", "获得", 0.9, '[{"text":"旧状态证据"}]'),
            )
            await db.commit()

            legacy_repo = SqliteNovelRepository(db)
            assert (await legacy_repo.get_relationships("user:1", book.id, limit=10))[0].evidence == [{"text": "旧库证据"}]
            assert (await legacy_repo.get_events("user:1", book.id, limit=10))[0].evidence == [{"text": "旧事件证据"}]
            assert (await legacy_repo.get_state_changes("user:1", book.id, limit=10))[0].evidence == [{"text": "旧状态证据"}]
        finally:
            await db.close()

    @staticmethod
    async def _save_book_for_repo(db, url):
        return await SqliteNovelRepository(db).save_book(
            "user:1", NovelBook(book_url=url, book_name="旧库证据书", owner_scope="user:1")
        )

    async def test_entity_evidence_is_merged_across_snapshots(self, repo):
        book = await repo.save_book(
            "user:1", NovelBook(book_url="https://entity-evidence.test", owner_scope="user:1")
        )
        await repo.replace_book_knowledge(
            "user:1",
            book.id,
            [
                {
                    "chapter_id": 1,
                    "chapter_num": 1,
                    "entities": [
                        {
                            "name": "江轩",
                            "entity_type": "character",
                            "appearance_count": 1,
                            "attributes": {"evidence": [{"text": "第一处证据"}], "source": "local"},
                        }
                    ],
                },
                {
                    "chapter_id": 2,
                    "chapter_num": 2,
                    "entities": [
                        {
                            "name": "江轩",
                            "entity_type": "character",
                            "appearance_count": 1,
                            "attributes": {"evidence": [{"text": "第二处证据"}], "source": "later"},
                        }
                    ],
                },
            ],
        )

        entity = (await repo.list_entities("user:1", book.id, limit=10))[0]
        assert {item["text"] for item in entity.attributes["evidence"]} == {"第一处证据", "第二处证据"}

    async def test_adjudication_candidate_round_trips_and_updates_status(self, repo):
        from app.domain.entities.novel_runtime import NovelAdjudicationCandidate

        book = await repo.save_book(
            "user:1", NovelBook(book_url="https://adjudication.test", owner_scope="user:1")
        )
        candidate = NovelAdjudicationCandidate(
            owner_scope="user:1",
            book_id=book.id,
            chapter_id=0,
            candidate_key="candidate:江轩",
            content_hash="hash-candidate",
            candidate_payload={"name": "江轩", "status": "candidate"},
            evidence_payload=[{"id": "e1", "text": "证据"}],
        )

        saved = await repo.upsert_adjudication_candidate(candidate)
        assert saved.id > 0
        pending = await repo.list_adjudication_candidates("user:1", book.id, status="pending")
        assert pending[0].candidate_payload["name"] == "江轩"

        assert await repo.update_adjudication_candidate(
            "user:1",
            saved.id,
            status="accept",
            decision={"verdict": "accept", "evidence_ids": ["e1"]},
            attempts=1,
        )
        accepted = await repo.list_adjudication_candidates("user:1", book.id, status="accept")
        assert accepted[0].decision["verdict"] == "accept"
        assert accepted[0].attempts == 1

    async def test_claim_legacy_scope_moves_adjudication_candidates(self, repo):
        from app.domain.entities.novel_runtime import NovelAdjudicationCandidate

        book = await repo.save_book(
            "legacy", NovelBook(book_url="https://legacy-adjudication.test", owner_scope="legacy")
        )
        await repo.upsert_adjudication_candidate(
            NovelAdjudicationCandidate(
                owner_scope="legacy",
                book_id=book.id,
                chapter_id=1,
                candidate_key="candidate:legacy",
                candidate_payload={"name": "旧候选"},
            )
        )

        counts = await repo.claim_legacy_scope("user:42")

        assert counts["novel_adjudication_candidates"] == 1
        candidates = await repo.list_adjudication_candidates("user:42", book.id)
        assert [item.candidate_payload["name"] for item in candidates] == ["旧候选"]
