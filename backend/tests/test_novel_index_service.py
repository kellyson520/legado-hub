import aiosqlite
import pytest
from pydantic import ValidationError


@pytest.fixture
async def index_service():
    from app.domain.entities.novel import NovelBook, NovelChapter
    from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository
    from app.infrastructure.vectorstores.disabled import DisabledVectorStore
    from app.services.novel_understanding.embedding import EmbeddingAdapter
    from app.services.novel_understanding.index_service import NovelIndexService

    db = await aiosqlite.connect(":memory:")
    with open("app/database_migrations/novel_schema.sql", encoding="utf-8") as schema:
        await db.executescript(schema.read())
    repo = SqliteNovelRepository(db)
    book = await repo.save_book("user:1", NovelBook(book_url="https://index.test/book", book_name="索引书"))
    await repo.save_chapter(
        "user:1",
        NovelChapter(
            book_id=book.id,
            canonical_full="C1",
            canonical_num=1,
            chapter_title="雨夜",
            raw_text="林远走进青云宗，周宁在门前等他。",
        ),
    )
    await repo.save_chapter(
        "user:1",
        NovelChapter(
            book_id=book.id,
            canonical_full="C2",
            canonical_num=2,
            chapter_title="决战",
            raw_text="林远与周宁在山谷决战。",
        ),
    )
    service = NovelIndexService(
        repo=repo,
        vector_store=DisabledVectorStore(),
        embedding=EmbeddingAdapter(),
    )
    try:
        yield service, book.id
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_changed_chapter_is_reindexed_without_reprocessing_unchanged_chapters(index_service):
    service, book_id = index_service

    first = await service.index_book("user:1", book_id=book_id)
    second = await service.index_book("user:1", book_id=book_id)
    assert first.processed_chapters == 2
    assert second.processed_chapters == 0

    await service.repo.update_chapter_content("user:1", chapter_id=2, content="林远与周宁在城门决战")
    changed = await service.index_book("user:1", book_id=book_id)
    assert changed.processed_chapters == 1
    assert changed.skipped_chapters == 1


@pytest.mark.asyncio
async def test_index_includes_chapters_with_zero_canonical_number(index_service):
    from app.domain.entities.novel import NovelChapter

    service, book_id = index_service
    await service.repo.save_chapter(
        "user:1",
        NovelChapter(
            book_id=book_id,
            canonical_type="P",
            canonical_full="P0",
            canonical_num=0,
            chapter_title="序章",
            raw_text="江轩在序章中出现。",
        ),
    )

    result = await service.index_book("user:1", book_id=book_id)

    assert result.processed_chapters == 3
    states = await service.repo.list_index_states("user:1", book_id)
    assert len(states) == 3
    assert all(state.extraction_payload.get("chapter_id") is not None for state in states)


@pytest.mark.asyncio
async def test_structured_events_and_relationships_are_validated_and_deduplicated(index_service):
    from app.infrastructure.vectorstores.disabled import DisabledVectorStore
    from app.services.novel_understanding.embedding import EmbeddingAdapter
    from app.services.novel_understanding.index_service import NovelIndexService
    from app.services.novel_understanding.structured_extractor import StructuredExtractor

    service, book_id = index_service

    class StructuredFixture:
        def extract_from_chapter(self, _book_id, chapter_num, _title, _text):
            if chapter_num != 1:
                return {"entities": [], "relationships": []}
            relationship = {
                "source_entity": "林远",
                "target_entity": "周宁",
                "relation_type": "ally",
                "description": "并肩作战",
                "confidence": 0.8,
                "evidence": [{"chapter_id": 1, "text": "林远走进青云宗"}],
            }
            event = {
                "chapter_id": 1,
                "event_type": "battle",
                "description": "并肩作战",
                "participants": ["林远", "周宁"],
                "importance": 4,
                "confidence": 0.8,
                "evidence": [{"chapter_id": 1, "text": "林远走进青云宗"}],
            }
            return {
                "entities": [],
                "relationships": [],
                "structured": {
                    "summary": "",
                    "relationships": [relationship, relationship],
                    "events": [event, event],
                    "state_changes": [],
                    "arc_tag": "",
                },
            }

    service = NovelIndexService(
        repo=service.repo,
        extractor=StructuredFixture(),
        structured_extractor=StructuredExtractor(),
        vector_store=DisabledVectorStore(),
        embedding=EmbeddingAdapter(),
    )
    result = await service.index_book("user:1", book_id=book_id)

    assert result.failed_chapters == 0
    assert len(await service.repo.get_relationships("user:1", book_id, limit=100)) == 1
    assert len(await service.repo.get_events("user:1", book_id, limit=100)) == 1


@pytest.mark.asyncio
async def test_failed_chapter_is_recorded_and_does_not_stop_following_chapters(index_service):
    from app.infrastructure.vectorstores.disabled import DisabledVectorStore
    from app.services.novel_understanding.embedding import EmbeddingAdapter
    from app.services.novel_understanding.index_service import NovelIndexService

    base, book_id = index_service

    class FailingFixture:
        def extract_from_chapter(self, _book_id, chapter_num, _title, _text):
            if chapter_num == 1:
                raise RuntimeError("chapter extraction failed")
            return [], []

    service = NovelIndexService(
        repo=base.repo,
        extractor=FailingFixture(),
        vector_store=DisabledVectorStore(),
        embedding=EmbeddingAdapter(),
    )
    result = await service.index_book("user:1", book_id=book_id)

    assert result.failed_chapters == 1
    assert result.processed_chapters == 1
    assert result.errors[0]["chapter_id"] == 1


@pytest.mark.asyncio
async def test_vector_backend_failure_keeps_local_chapter_index_available(index_service):
    from app.services.novel_understanding.embedding import EmbeddingAdapter
    from app.services.novel_understanding.index_service import NovelIndexService

    base, book_id = index_service

    class BrokenVectorStore:
        async def health(self):
            raise RuntimeError("vector backend offline")

    service = NovelIndexService(
        repo=base.repo,
        vector_store=BrokenVectorStore(),
        embedding=EmbeddingAdapter(),
    )
    result = await service.index_book("user:1", book_id=book_id)

    assert result.failed_chapters == 0
    assert result.processed_chapters == 2
    state = await service.repo.get_index_state("user:1", book_id, chapter_id=1)
    assert state.vector_status == "failed"


@pytest.mark.asyncio
async def test_semantic_vector_index_keeps_chapter_and_memory_card_records(index_service):
    from app.domain.entities.novel import EntityType, NovelEntity
    from app.infrastructure.vectorstores.disabled import DisabledVectorStore
    from app.services.novel_understanding.embedding import EmbeddingAdapter
    from app.services.novel_understanding.index_service import NovelIndexService

    base, book_id = index_service
    chapter = await base.repo.get_chapters_by_book("user:1", book_id, start_num=1, limit=1)
    chapter = chapter[0]
    await base.repo.update_chapter_content(
        "user:1",
        chapter.id,
        "江轩从石匣中取出玄天剑，剑身泛起寒光。",
    )

    class Extractor:
        def extract_from_chapter(self, current_book_id, chapter_num, title, text):
            return [
                NovelEntity(
                    book_id=current_book_id,
                    name="玄天剑",
                    entity_type=EntityType.ITEM,
                    first_appearance_ch=chapter_num,
                    last_appearance_ch=chapter_num,
                    appearance_count=1,
                    attributes={"confidence": 0.9, "evidence": [{"chapter_id": chapter.id, "text": text}]},
                )
            ], []

    class Embedding:
        model = "semantic-test"

        async def embed_batch(self, texts):
            return [
                type(
                    "Embedding",
                    (),
                    {"semantic": True, "vector": [1.0, 0.0], "model": self.model, "dimension": 2},
                )()
                for _ in texts
            ]

    class Store:
        def __init__(self):
            self.records = []

        async def health(self):
            return {"enabled": True}

        async def upsert(self, records):
            self.records.extend(records)
            return len(records)

    store = Store()
    service = NovelIndexService(
        repo=base.repo,
        extractor=Extractor(),
        embedding=Embedding(),
        vector_store=store,
    )
    result = await service.index_book("user:1", book_id)

    assert result.failed_chapters == 0
    assert {record.record_key for record in store.records} >= {"chapter:1", "entity:item:玄天剑"}
    assert all(record.payload.get("card_hash") for record in store.records)


@pytest.mark.asyncio
async def test_index_service_sends_only_ambiguous_local_candidates_to_adjudicator(index_service):
    from app.domain.entities.novel import EntityType, NovelEntity
    from app.services.novel_understanding.index_service import NovelIndexService

    base, book_id = index_service

    class Extractor:
        def extract_from_chapter(self, current_book_id, chapter_num, title, text):
            return [
                NovelEntity(
                    book_id=current_book_id,
                    name="江轩",
                    entity_type=EntityType.CHARACTER,
                    first_appearance_ch=chapter_num,
                    last_appearance_ch=chapter_num,
                    appearance_count=1,
                    attributes={
                        "extraction_status": "candidate",
                        "confidence": 0.4,
                        "evidence": [{"chapter_id": 1, "text": text}],
                    },
                )
            ], []

    class Adjudicator:
        def __init__(self):
            self.candidates = []

        async def adjudicate(self, owner_scope, current_book_id, candidates):
            self.candidates.extend(candidates)
            return [{"name": "江轩", "verdict": "accept", "evidence_ids": [], "source": "agent"}]

    adjudicator = Adjudicator()
    service = NovelIndexService(
        repo=base.repo,
        extractor=Extractor(),
        adjudicator=adjudicator,
    )

    result = await service.index_book("user:1", book_id)

    assert result.failed_chapters == 0
    assert adjudicator.candidates
    assert all(item["status"] in {"candidate", "conflict"} for item in adjudicator.candidates)


@pytest.mark.asyncio
async def test_empty_book_rebuilds_knowledge_projection(index_service):
    from app.domain.entities.novel import NovelBook

    service, _ = index_service
    empty_book = await service.repo.save_book(
        "user:1", NovelBook(book_url="https://index.test/empty", book_name="空书")
    )
    await service.repo.replace_book_knowledge(
        "user:1",
        empty_book.id,
        [{"chapter_id": 1, "chapter_num": 1, "entities": [{"name": "旧人物", "entity_type": "character"}]}],
    )
    assert (await service.repo.get_book_by_id("user:1", empty_book.id)).character_count == 1

    result = await service.index_book("user:1", empty_book.id)

    assert result.processed_chapters == 0
    refreshed = await service.repo.get_book_by_id("user:1", empty_book.id)
    assert refreshed.character_count == 0
    assert refreshed.entity_count == 0


@pytest.mark.asyncio
async def test_adjudication_decision_is_forwarded_to_book_learning(index_service):
    from app.domain.entities.novel import EntityType, NovelEntity
    from app.services.novel_understanding.index_service import NovelIndexService

    base, book_id = index_service

    class Learning:
        def __init__(self):
            self.calls = []

        async def get_profile(self, _owner_scope, _book_id):
            return {}

        async def learn_from_adjudication(self, owner_scope, learned_book_id, candidate, decision):
            self.calls.append((owner_scope, learned_book_id, candidate, decision))

    class Extractor:
        def set_learning_profile(self, _profile):
            return None

        def extract_with_evidence(self, chapter_book_id, chapter_num, _title, _text, *, chapter_id):
            return [
                NovelEntity(
                    book_id=chapter_book_id,
                    name="江轩",
                    entity_type=EntityType.CHARACTER,
                    description="候选人物",
                    first_appearance_ch=chapter_num,
                    last_appearance_ch=chapter_num,
                    appearance_count=1,
                    importance_score=2,
                    attributes={
                        "extraction_status": "candidate",
                        "confidence": 0.5,
                        "mention_count": 1,
                        "evidence": [{"chapter_id": chapter_id, "text": "江轩"}],
                    },
                )
            ], []

    class Adjudicator:
        async def adjudicate(self, _owner_scope, _book_id, candidates):
            return [
                {
                    "name": candidates[0]["name"],
                    "entity_type": candidates[0]["entity_type"],
                    "verdict": "accept",
                    "evidence_ids": ["evidence-1"],
                }
            ]

    learning = Learning()
    service = NovelIndexService(
        repo=base.repo,
        extractor=Extractor(),
        adjudicator=Adjudicator(),
        adaptive_learning=learning,
        vector_store=None,
        embedding=None,
    )

    result = await service.index_book("user:1", book_id)

    assert result.failed_chapters == 0
    assert len(learning.calls) == 2
    assert {call[0] for call in learning.calls} == {"user:1"}
    assert {call[1] for call in learning.calls} == {book_id}
    assert all(call[2]["name"] == "江轩" for call in learning.calls)
    assert all(call[2]["content_hash"] for call in learning.calls)
    assert all(call[3]["verdict"] == "accept" for call in learning.calls)


@pytest.mark.asyncio
async def test_structured_failure_is_retried_instead_of_being_skipped(index_service):
    from app.infrastructure.vectorstores.disabled import DisabledVectorStore
    from app.services.novel_understanding.embedding import EmbeddingAdapter
    from app.services.novel_understanding.index_service import NovelIndexService
    from app.services.novel_understanding.structured_extractor import StructuredExtractor

    base, book_id = index_service

    class Extractor:
        def extract_from_chapter(self, current_book_id, chapter_num, title, text):
            return {"entities": [], "relationships": [], "structured": {
                "summary": "",
                "relationships": [],
                "events": [],
                "state_changes": [],
                "arc_tag": "",
            }}

    class FailOnceStructuredExtractor(StructuredExtractor):
        def __init__(self):
            self.calls = 0

        @classmethod
        def parse(cls, payload, *, chapter_id, chapter_text):
            return StructuredExtractor.parse(payload, chapter_id=chapter_id, chapter_text=chapter_text)

    validator = FailOnceStructuredExtractor()
    original_parse = validator.parse

    def parse_once(payload, *, chapter_id, chapter_text):
        validator.calls += 1
        if validator.calls == 1:
            raise ValueError("temporary structured failure")
        return StructuredExtractor.parse(payload, chapter_id=chapter_id, chapter_text=chapter_text)

    validator.parse = parse_once
    service = NovelIndexService(
        repo=base.repo,
        extractor=Extractor(),
        structured_extractor=validator,
        vector_store=DisabledVectorStore(),
        embedding=EmbeddingAdapter(),
    )

    first = await service.index_book("user:1", book_id)
    assert first.processed_chapters == 2
    failed_state = await service.repo.get_index_state("user:1", book_id, chapter_id=1)
    assert failed_state.extraction_payload["structured_status"] == "failed"

    second = await service.index_book("user:1", book_id)

    assert second.processed_chapters == 1
    assert second.skipped_chapters == 1
    recovered = await service.repo.get_index_state("user:1", book_id, chapter_id=1)
    assert recovered.extraction_payload["structured_status"] == "completed"


@pytest.mark.asyncio
async def test_learning_profile_is_loaded_per_book_and_profile_changes_reindex(index_service):
    from app.application.services.novel_understanding.index_service import NovelIndexService

    base, book_id = index_service
    await base.repo.update_chapter_content("user:1", chapter_id=1, content="他自称小轩，江边没有回应。")

    class LearningProfile:
        def __init__(self):
            self.profile = {
                "profile_version": "learning-v1:test",
                "aliases": {"小轩": "江轩"},
                "negative_terms": ["江边"],
                "feature_weights": {"explicit_name": 1.5},
            }
            self.calls = []

        async def get_profile(self, owner_scope, current_book_id):
            self.calls.append((owner_scope, current_book_id))
            return dict(self.profile)

    learning = LearningProfile()
    service = NovelIndexService(repo=base.repo, adaptive_learning=learning)

    first = await service.index_book("user:1", book_id)

    assert first.processed_chapters == 2
    entity = await base.repo.get_entity_by_name("user:1", book_id, "江轩")
    assert entity is not None
    assert await base.repo.get_entity_by_name("user:1", book_id, "小轩") is None
    state = await base.repo.get_index_state("user:1", book_id, chapter_id=1)
    assert state.extraction_payload["learning_profile_version"] == "learning-v1:test"

    learning.profile = {
        **learning.profile,
        "profile_version": "learning-v1:changed",
    }
    second = await service.index_book("user:1", book_id)

    assert second.processed_chapters == 2
    assert learning.calls == [("user:1", book_id), ("user:1", book_id)]


@pytest.mark.asyncio
async def test_failed_reindex_keeps_last_successful_snapshot(index_service):
    from app.infrastructure.vectorstores.disabled import DisabledVectorStore
    from app.services.novel_understanding.embedding import EmbeddingAdapter
    from app.services.novel_understanding.index_service import NovelIndexService

    base, book_id = index_service
    first = await base.index_book("user:1", book_id)
    assert first.failed_chapters == 0
    before_entities = await base.repo.list_entities("user:1", book_id, limit=100)
    assert before_entities
    before_names = {entity.name for entity in before_entities}
    await base.repo.update_chapter_content("user:1", chapter_id=1, content="林远在城门遇见周宁。")

    class FailingExtractor:
        def extract_from_chapter(self, *_args):
            raise RuntimeError("temporary extraction failure")

    service = NovelIndexService(
        repo=base.repo,
        extractor=FailingExtractor(),
        vector_store=DisabledVectorStore(),
        embedding=EmbeddingAdapter(),
    )
    result = await service.index_book("user:1", book_id)

    assert result.failed_chapters == 1
    assert result.skipped_chapters == 1
    state = await service.repo.get_index_state("user:1", book_id, chapter_id=1)
    assert state.extraction_status == "failed"
    assert state.extraction_payload["entities"]
    after_names = {entity.name for entity in await service.repo.list_entities("user:1", book_id, limit=100)}
    assert after_names == before_names


@pytest.mark.asyncio
async def test_changed_chapter_removes_stale_vector_memory_cards(index_service):
    from app.services.novel_understanding.index_service import NovelIndexService
    from app.services.novel_understanding.structured_extractor import StructuredExtractor

    base, book_id = index_service

    class Extractor:
        def extract_from_chapter(self, _book_id, chapter_num, _title, text):
            if chapter_num != 1:
                return [], []
            marker = "旧事件" if "旧" in text else "新事件"
            return [], [], {
                "summary": marker,
                "relationships": [],
                "events": [{
                    "chapter_id": 1,
                    "event_type": "discovery",
                    "description": marker,
                    "participants": ["林远"],
                    "importance": 3,
                    "confidence": 0.9,
                    "evidence": [{"chapter_id": 1, "text": text}],
                }],
                "state_changes": [],
                "arc_tag": "",
            }

    class Embedding:
        model = "vector-test"

        async def embed_batch(self, texts):
            return [type("Embedding", (), {
                "semantic": True,
                "vector": [1.0, 0.0],
                "model": self.model,
                "dimension": 2,
            })() for _ in texts]

    class Store:
        def __init__(self):
            self.records = {}

        async def health(self):
            return {"enabled": True}

        async def upsert(self, records):
            self.records.update({record.record_key: record for record in records})
            return len(records)

        async def delete_chapter(self, owner_scope, current_book_id, chapter_id, knowledge_version=None):
            del owner_scope, current_book_id, knowledge_version
            keys = [key for key, record in self.records.items() if record.chapter_id == chapter_id]
            for key in keys:
                self.records.pop(key, None)
            return len(keys)

    store = Store()
    service = NovelIndexService(
        repo=base.repo,
        extractor=Extractor(),
        structured_extractor=StructuredExtractor(),
        embedding=Embedding(),
        vector_store=store,
    )
    await base.repo.update_chapter_content("user:1", chapter_id=1, content="旧事件证据")
    assert (await service.index_book("user:1", book_id)).failed_chapters == 0
    old_keys = set(store.records)
    old_event_keys = {key for key in old_keys if key.startswith("event:1:")}
    assert old_event_keys

    await base.repo.update_chapter_content("user:1", chapter_id=1, content="新事件证据")
    assert (await service.index_book("user:1", book_id)).failed_chapters == 0

    new_keys = set(store.records)
    assert not old_event_keys.intersection(new_keys)
    assert len([key for key in new_keys if key.startswith("event:1:")]) == 1


@pytest.mark.asyncio
async def test_failed_vector_state_is_retried(index_service):
    from app.services.novel_understanding.embedding import EmbeddingAdapter
    from app.services.novel_understanding.index_service import NovelIndexService

    base, book_id = index_service

    class BrokenVectorStore:
        async def health(self):
            raise RuntimeError("vector backend offline")

    service = NovelIndexService(
        repo=base.repo,
        embedding=EmbeddingAdapter(),
        vector_store=BrokenVectorStore(),
    )

    first = await service.index_book("user:1", book_id)
    second = await service.index_book("user:1", book_id)

    assert first.processed_chapters == 2
    assert second.processed_chapters == 2
    assert second.skipped_chapters == 0


def test_structured_extractor_rejects_unknown_fields_and_unbound_evidence():
    from app.services.novel_understanding.structured_extractor import StructuredExtractor

    valid = {
        "summary": "林远进入青云宗。",
        "relationships": [
            {
                "source_entity": "林远",
                "target_entity": "周宁",
                "relation_type": "ally",
                "description": "并肩作战",
                "confidence": 0.8,
                "evidence": [{"chapter_id": 1, "text": "林远与周宁并肩作战"}],
            }
        ],
        "events": [],
        "state_changes": [],
        "arc_tag": "入门",
    }
    parsed = StructuredExtractor.parse(valid, chapter_id=1, chapter_text="林远与周宁并肩作战")
    assert parsed.relationships[0].evidence[0].chapter_id == 1

    with pytest.raises(ValidationError):
        StructuredExtractor.parse({**valid, "unexpected": True}, chapter_id=1, chapter_text="林远与周宁并肩作战")
    with pytest.raises(ValueError, match="evidence"):
        StructuredExtractor.parse(
            {
                **valid,
                "relationships": [
                    {
                        **valid["relationships"][0],
                        "evidence": [{"chapter_id": 2, "text": "不在本章"}],
                    }
                ],
            },
            chapter_id=1,
            chapter_text="林远与周宁并肩作战",
        )
