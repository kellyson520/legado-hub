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
