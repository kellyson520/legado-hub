from fastapi.testclient import TestClient


def test_work_knowledge_proposal_and_review_flow(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-work-knowledge.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    token = create_access_token({'sub': '1', 'permissions': ['novel.manage'], 'sid': 'knowledge-1'})
    client = TestClient(app)
    headers = {'Authorization': f'Bearer {token}'}

    created = client.post(
        '/api/work-knowledge/relations',
        headers=headers,
        json={
            'work_id': 'w1',
            'source_chapter_id': 'c1',
            'evidence': 'Lin trusts Mei',
            'relation': 'trusts',
        },
    )

    assert created.status_code == 200
    assert created.json()['data']['status'] == 'candidate'
    proposal_id = created.json()['data']['id']

    published_before = client.get('/api/work-knowledge/works/w1/relations', headers=headers)
    assert published_before.status_code == 200
    assert published_before.json()['data'] == []

    resolved = client.post(
        f'/api/work-knowledge/reviews/{proposal_id}/resolve',
        headers=headers,
        json={'action': 'publish'},
    )
    assert resolved.status_code == 200
    assert resolved.json()['data']['status'] == 'published'

    published_after = client.get('/api/work-knowledge/works/w1/relations', headers=headers)
    assert published_after.status_code == 200
    assert published_after.json()['data'][0]['relation'] == 'trusts'


def test_work_knowledge_requires_novel_manage(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-work-knowledge-perm.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    token = create_access_token({'sub': '1', 'permissions': ['book_sources.read'], 'sid': 'knowledge-2'})
    client = TestClient(app)

    response = client.post(
        '/api/work-knowledge/relations',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'work_id': 'w1',
            'source_chapter_id': 'c1',
            'evidence': 'Lin trusts Mei',
            'relation': 'trusts',
        },
    )

    assert response.status_code == 403
    assert response.json()['code'] == 'AUTHORIZATION_ERROR'


def test_plot_event_and_world_rule_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-work-knowledge-extra.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    token = create_access_token({'sub': '1', 'permissions': ['novel.manage'], 'sid': 'knowledge-3'})
    client = TestClient(app)
    headers = {'Authorization': f'Bearer {token}'}

    plot = client.post(
        '/api/work-knowledge/plot-events',
        headers=headers,
        json={
            'work_id': 'w1',
            'source_chapter_id': 'c2',
            'evidence': 'Lin enters the forbidden cave and finds an ancient map.',
            'event_title': 'Forbidden cave discovery',
            'summary': 'The protagonist discovers an ancient map in the cave.',
        },
    )
    world = client.post(
        '/api/work-knowledge/world-rules',
        headers=headers,
        json={
            'work_id': 'w1',
            'source_chapter_id': 'c3',
            'evidence': 'Only silver fire can break the veil.',
            'rule_name': 'Silver fire breaks the veil',
            'description': 'Silver fire is the only force capable of breaking the veil.',
        },
    )

    assert plot.status_code == 200
    assert plot.json()['data']['proposal_type'] == 'plot_event'
    assert world.status_code == 200
    assert world.json()['data']['proposal_type'] == 'world_rule'


def test_operations_review_queue_lists_candidate_proposals(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-review-queue.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.domain.entities.translation_runtime import TranslationJob
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.translation_runtime_repo_impl import SQLiteTranslationRuntimeRepository
    from app.main import app

    bootstrap_sqlite()
    token = create_access_token({'sub': '1', 'permissions': ['novel.manage', 'agent_runs.read'], 'sid': 'knowledge-4'})
    client = TestClient(app)
    headers = {'Authorization': f'Bearer {token}'}

    created = client.post(
        '/api/work-knowledge/relations',
        headers=headers,
        json={
            'work_id': 'w-review',
            'source_chapter_id': 'c-review',
            'evidence': 'Lin trusts Mei',
            'relation': 'trusts',
        },
    )
    assert created.status_code == 200

    SQLiteTranslationRuntimeRepository().save_job(
        TranslationJob(
            id='translation-review-1',
            actor_id='translator-1',
            source_language='zh',
            target_language='en',
            status='succeeded',
            provider='memory-llm',
            model='gpt-4.1-mini',
            source_text='原文内容',
            result_text='Translated content preview',
            content_variant_id='variant-1',
            review_status='candidate',
            chunk_count=2,
        )
    )

    response = client.get('/api/events/review-queue', headers=headers)

    assert response.status_code == 200
    rows = response.json()['data']
    knowledge_row = next(row for row in rows if row['proposal_type'] == 'character_relation')
    translation_row = next(row for row in rows if row['proposal_type'] == 'translation_review')

    assert knowledge_row['work_id'] == 'w-review'
    assert knowledge_row['item_type'] == 'knowledge_proposal'
    assert knowledge_row['status'] == 'candidate'

    assert translation_row['item_type'] == 'translation_job'
    assert translation_row['source_chapter_id'] == 'variant-1'
    assert translation_row['status'] == 'candidate'
    assert translation_row['created_by'] == 'translator-1'

    actor_search = client.get(
        '/api/events/review-queue?search=translator-1',
        headers=headers,
    )
    assert actor_search.status_code == 200
    assert actor_search.json()['meta']['total'] == 1
    assert actor_search.json()['data'][0]['id'] == 'translation-review-1'


def test_operations_review_queue_paginates_all_source_candidates(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-review-queue-pagination.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_source_runtime_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    repo = build_source_runtime_repository()
    for index in range(55):
        repo.create_candidate_version(
            source_type='book',
            source_id=f'https://example.test/books/{index:02d}',
            payload={'canonical_url': f'https://example.test/books/{index:02d}'},
            created_by='pagination-test',
        )

    token = create_access_token({'sub': '1', 'permissions': ['agent_runs.read']})
    response = TestClient(app).get(
        '/api/events/review-queue?page=2&page_size=50',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['meta']['total'] == 55
    assert payload['meta']['total_pages'] == 2
    assert len(payload['data']) == 5
    assert all(item['item_type'] == 'source_version' for item in payload['data'])

    source_type_search = TestClient(app).get(
        '/api/events/review-queue?page=2&page_size=50&search=book',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert source_type_search.status_code == 200
    assert source_type_search.json()['meta']['total'] == 55
    assert len(source_type_search.json()['data']) == 5

    oversized_page = TestClient(app).get(
        '/api/events/review-queue?page=101&page_size=200',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert oversized_page.status_code == 422


def test_operations_review_queue_can_publish_knowledge_proposal(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-review-queue-resolve.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    token = create_access_token({'sub': '1', 'permissions': ['novel.manage', 'agent_runs.write'], 'sid': 'knowledge-5'})
    client = TestClient(app)
    headers = {'Authorization': f'Bearer {token}'}

    created = client.post(
        '/api/work-knowledge/relations',
        headers=headers,
        json={
            'work_id': 'w-review',
            'source_chapter_id': 'c-review',
            'evidence': 'Lin trusts Mei',
            'relation': 'trusts',
        },
    )
    assert created.status_code == 200
    proposal_id = created.json()['data']['id']

    response = client.post(
        f'/api/events/review-queue/{proposal_id}/resolve',
        headers=headers,
        json={'item_type': 'knowledge_proposal', 'action': 'publish'},
    )

    assert response.status_code == 200
    assert response.json()['data']['queue_item_id'] == proposal_id
    assert response.json()['data']['item_type'] == 'knowledge_proposal'
    assert response.json()['data']['status'] == 'published'
