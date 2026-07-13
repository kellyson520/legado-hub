import asyncio

from fastapi.testclient import TestClient


def test_client_reading_lists_works_toc_and_chapters(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-client-reading.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import generate_api_key, hash_api_key
    from app.domain.entities.auth import ApiKey
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_canonical_content_service

    bootstrap_sqlite()
    raw_key = generate_api_key()
    asyncio.run(
        SQLiteAuthRepository().save_api_key(
            ApiKey(
                name='reader',
                key_hash=hash_api_key(raw_key),
                permissions=['read.work', 'read.toc', 'read.chapter'],
            )
        )
    )

    canonical = build_canonical_content_service()
    work = canonical.create_canonical_work(title='Demo Book', author='Tester')
    chapter = canonical.add_canonical_chapters(work.id, ['Chapter 1'])[0]
    source_work = canonical.create_source_work(
        canonical_work_id=work.id,
        source_id='source-a',
        title='Demo Book',
        author='Tester',
    )
    source_chapter = canonical.add_source_chapter(
        source_work.id,
        title='Chapter 1',
        chapter_url='https://source-a.test/book/1',
        chapter_index=0,
    )
    canonical.save_alignment(
        canonical_chapter_id=chapter.id,
        source_chapter_id=source_chapter.id,
        confidence=1.0,
        evidence={'match': 'exact'},
        review_status='accepted',
    )
    canonical.add_content_variant(
        canonical_chapter_id=chapter.id,
        source_chapter_id=source_chapter.id,
        source_id='source-a',
        content='正文内容',
        health_status='healthy',
        quality_score=0.95,
        coverage_score=0.95,
        freshness_score=0.95,
        latency_ms=50,
    )

    from app.main import app

    client = TestClient(app)
    headers = {'Authorization': f'Bearer {raw_key}'}

    works = client.get('/api/client/works', headers=headers)
    toc = client.get(f'/api/client/works/{work.id}/toc', headers=headers)
    chapter_response = client.get(f'/api/client/chapters/{chapter.id}', headers=headers)

    assert works.status_code == toc.status_code == chapter_response.status_code == 200
    assert works.json()['data'][0]['title'] == 'Demo Book'
    assert toc.json()['data'][0]['title'] == 'Chapter 1'
    assert chapter_response.json()['data']['content'] == '正文内容'
    assert chapter_response.json()['meta']['route_summary']['selected_source_id'] == 'source-a'


def test_client_reading_requires_chapter_capability(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-client-reading-perm.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import generate_api_key, hash_api_key
    from app.domain.entities.auth import ApiKey
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    raw_key = generate_api_key()
    asyncio.run(
        SQLiteAuthRepository().save_api_key(
            ApiKey(name='limited-reader', key_hash=hash_api_key(raw_key), permissions=['read.work', 'read.toc'])
        )
    )

    from app.main import app

    response = TestClient(app).get('/api/client/chapters/missing', headers={'Authorization': f'Bearer {raw_key}'})

    assert response.status_code == 403
    assert response.json()['message'] == 'Permission denied: read.chapter'
