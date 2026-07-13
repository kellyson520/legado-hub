import pytest


class EchoTranslationPlatform:
    async def invoke_chat(
        self,
        provider_group: str,
        model: str,
        payload: dict,
        quota_scope: tuple[str, str],
    ) -> dict:
        return {
            'provider_name': 'memory-llm',
            'model': model,
            'output': {'text': payload['text'][::-1]},
            'usage': {'input_tokens': len(payload['text']), 'output_tokens': len(payload['text'])},
        }


def test_character_relation_is_candidate_until_reviewed(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'work-knowledge.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_work_knowledge_service

    bootstrap_sqlite()
    service = build_work_knowledge_service()

    proposal = service.propose_relation(
        work_id='w1',
        source_chapter_id='c1',
        evidence='Lin trusts Mei',
        relation='trusts',
    )

    assert proposal.status == 'candidate'
    assert service.list_published_relations('w1') == []


def test_review_resolve_publishes_immutable_relation_revision(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'work-knowledge-review.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_work_knowledge_service

    bootstrap_sqlite()
    service = build_work_knowledge_service()
    proposal = service.propose_relation(
        work_id='w1',
        source_chapter_id='c1',
        evidence='Lin trusts Mei',
        relation='trusts',
    )

    published = service.resolve_review(proposal.id, action='publish', reviewer_id='reviewer-1')
    relations = service.list_published_relations('w1')

    assert published.status == 'published'
    assert published.revision_of == proposal.id
    assert relations[0].id == published.id
    assert relations[0].relation == 'trusts'


def test_plot_event_is_candidate_until_reviewed(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'work-knowledge-plot.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_work_knowledge_service

    bootstrap_sqlite()
    service = build_work_knowledge_service()

    proposal = service.propose_plot_event(
        work_id='w1',
        source_chapter_id='c2',
        evidence='Lin enters the forbidden cave and finds an ancient map.',
        event_title='Forbidden cave discovery',
        summary='The protagonist discovers an ancient map in the cave.',
    )

    assert proposal.status == 'candidate'
    assert service.list_published_plot_events('w1') == []


def test_world_rule_can_be_published_after_review(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'work-knowledge-world.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_work_knowledge_service

    bootstrap_sqlite()
    service = build_work_knowledge_service()

    proposal = service.propose_world_rule(
        work_id='w1',
        source_chapter_id='c3',
        evidence='Only silver fire can break the veil.',
        rule_name='Silver fire breaks the veil',
        description='Silver fire is the only force capable of breaking the veil.',
    )
    published = service.resolve_review(proposal.id, action='publish', reviewer_id='reviewer-2')

    rules = service.list_published_world_rules('w1')
    assert published.status == 'published'
    assert rules[0].id == published.id
    assert rules[0].payload['rule_name'] == 'Silver fire breaks the veil'


@pytest.mark.asyncio
async def test_translation_service_consumes_explicit_content_variant(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'translation-variant.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.translation_service import TranslationService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_canonical_content_repository
    from app.infrastructure.persistence.sqlite.translation_runtime_repo_impl import SQLiteTranslationRuntimeRepository

    bootstrap_sqlite()
    canonical_repo = build_canonical_content_repository()
    work = canonical_repo.create_canonical_work(title='Demo Book', author='Tester')
    chapter = canonical_repo.add_canonical_chapter(canonical_work_id=work.id, chapter_index=0, title='Chapter 1')
    source_work = canonical_repo.create_source_work(
        canonical_work_id=work.id,
        source_id='source-a',
        title='Demo Book',
        author='Tester',
    )
    source_chapter = canonical_repo.add_source_chapter(
        source_work_id=source_work.id,
        chapter_index=0,
        title='Chapter 1',
        chapter_url='https://source-a.test/book/1',
        canonical_chapter_id=chapter.id,
    )
    variant = canonical_repo.add_content_variant(
        canonical_chapter_id=chapter.id,
        source_chapter_id=source_chapter.id,
        source_id='source-a',
        content='正文内容',
        health_status='healthy',
        quality_score=0.9,
        coverage_score=0.9,
        freshness_score=0.9,
        latency_ms=20,
        is_verified=True,
    )

    service = TranslationService(
        platform=EchoTranslationPlatform(),
        repo=SQLiteTranslationRuntimeRepository(),
        canonical_repo=canonical_repo,
    )
    job = await service.create_job(
        {
            'content_variant_id': variant.id,
            'source_language': 'zh',
            'target_language': 'en',
        },
        actor_id='translator-1',
    )

    assert job['content_variant_id'] == variant.id
    assert job['source_text'] == '正文内容'
    assert job['review_status'] == 'candidate'


@pytest.mark.asyncio
async def test_translation_review_updates_memory_payload(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'translation-review.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.translation_service import TranslationService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.translation_runtime_repo_impl import SQLiteTranslationRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteTranslationRuntimeRepository()
    service = TranslationService(
        platform=EchoTranslationPlatform(),
        repo=repo,
    )

    job = await service.create_job(
        {
            'text': '正文内容',
            'source_language': 'zh',
            'target_language': 'en',
        },
        actor_id='translator-2',
    )
    reviewed = await service.review_job(
        job['id'],
        reviewer_id='editor-1',
        memory_note={'term': 'Lin', 'preferred_translation': 'Lin'},
    )

    assert reviewed['review_status'] == 'reviewed'
    assert reviewed['memory_payload']['reviewed_by'] == 'editor-1'
    assert reviewed['memory_payload']['notes'][0]['term'] == 'Lin'
