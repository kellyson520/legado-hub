import aiosqlite
import pytest

from app.domain.entities.novel import NovelBook
from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository


@pytest.fixture
async def learning_repo():
    db = await aiosqlite.connect(":memory:")
    with open("app/database_migrations/novel_schema.sql", encoding="utf-8") as schema:
        await db.executescript(schema.read())
    repo = SqliteNovelRepository(db)
    first = await repo.save_book("user:1", NovelBook(book_url="https://learning.test/1", owner_scope="user:1"))
    second = await repo.save_book("user:1", NovelBook(book_url="https://learning.test/2", owner_scope="user:1"))
    try:
        yield repo, first.id, second.id
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_repeated_evidence_activates_book_scoped_alias_and_negative_term(learning_repo):
    from app.application.services.novel_understanding.adaptive_learning import AdaptiveLearningService

    repo, book_id, other_book_id = learning_repo
    service = AdaptiveLearningService(repo=repo, min_support=2)

    await service.record_signal(
        "user:1", book_id, kind="alias", name="小轩", canonical_name="江轩", evidence_ids=["e1"], content_hash="h1"
    )
    assert (await service.get_profile("user:1", book_id))["aliases"] == {}
    await service.record_signal(
        "user:1", book_id, kind="alias", name="小轩", canonical_name="江轩", evidence_ids=["e2"], content_hash="h2"
    )
    await service.record_signal(
        "user:1", book_id, kind="negative", name="周围的", evidence_ids=["e3"], content_hash="h3"
    )
    await service.record_signal(
        "user:1", book_id, kind="negative", name="周围的", evidence_ids=["e4"], content_hash="h4"
    )

    profile = await service.get_profile("user:1", book_id)
    other_profile = await service.get_profile("user:1", other_book_id)
    assert profile["aliases"] == {"小轩": "江轩"}
    assert profile["negative_terms"] == ["周围的"]
    assert other_profile["aliases"] == {}
    assert other_profile["negative_terms"] == []


@pytest.mark.asyncio
async def test_chat_text_is_not_a_learning_signal_and_weights_are_bounded(learning_repo):
    from app.application.services.novel_understanding.adaptive_learning import AdaptiveLearningService

    repo, book_id, _ = learning_repo
    service = AdaptiveLearningService(repo=repo, min_support=2)

    assert await service.record_signal(
        "user:1", book_id, kind="alias", name="聊天里的词", canonical_name="另一个词", source="chat", content_hash="chat"
    ) is None
    await service.record_signal(
        "user:1", book_id, kind="weight", feature="explicit_name", delta=100, evidence_ids=["e1"], content_hash="h1", explicit=True
    )
    profile = await service.get_profile("user:1", book_id)
    assert profile["feature_weights"]["explicit_name"] == 1.5


@pytest.mark.asyncio
async def test_failed_learning_update_keeps_previous_profile(learning_repo):
    from app.application.services.novel_understanding.adaptive_learning import AdaptiveLearningService

    repo, book_id, _ = learning_repo
    service = AdaptiveLearningService(repo=repo, min_support=1)
    await service.record_signal(
        "user:1", book_id, kind="negative", name="旧误报", evidence_ids=["e1"], content_hash="h1", explicit=True
    )
    before = await service.get_profile("user:1", book_id)

    original = repo.apply_evolution_update

    async def failing_update(*args, **kwargs):
        raise RuntimeError("learning transaction failed")

    repo.apply_evolution_update = failing_update
    with pytest.raises(RuntimeError, match="learning transaction failed"):
        await service.record_signal(
            "user:1", book_id, kind="negative", name="新误报", evidence_ids=["e2"], content_hash="h2", explicit=True
        )
    repo.apply_evolution_update = original

    assert await service.get_profile("user:1", book_id) == before


@pytest.mark.asyncio
async def test_adjudication_alias_learning_maps_alias_to_canonical_name(learning_repo):
    from app.application.services.novel_understanding.adaptive_learning import AdaptiveLearningService

    repo, book_id, _ = learning_repo
    service = AdaptiveLearningService(repo=repo, min_support=1)

    await service.learn_from_adjudication(
        "user:1",
        book_id,
        {"name": "江轩", "aliases": ["小轩"]},
        {"verdict": "accept", "evidence_ids": ["e1"]},
    )

    assert (await service.get_profile("user:1", book_id))["aliases"] == {"小轩": "江轩"}
