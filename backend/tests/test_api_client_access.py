import asyncio

from fastapi.testclient import TestClient


def test_api_key_discovers_only_granted_capabilities(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'client-access.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import generate_api_key, hash_api_key
    from app.domain.entities.auth import ApiKey
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    raw_key = generate_api_key()
    asyncio.run(
        SQLiteAuthRepository().save_api_key(
            ApiKey(name='reader', key_hash=hash_api_key(raw_key), permissions=['read.work', 'read.toc'])
        )
    )

    from app.main import app

    response = TestClient(app).get('/api/capabilities', headers={'Authorization': f'Bearer {raw_key}'})

    assert response.status_code == 200
    assert response.json()['data']['capabilities'] == ['read.toc', 'read.work']
    assert response.json()['data']['principal']['api_key_name'] == 'reader'


def test_api_key_submits_an_idempotent_job(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'client-jobs.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import generate_api_key, hash_api_key
    from app.domain.entities.auth import ApiKey
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    raw_key = generate_api_key()
    asyncio.run(SQLiteAuthRepository().save_api_key(ApiKey(name='worker', key_hash=hash_api_key(raw_key), permissions=['events.read', 'jobs.submit'])))

    from app.main import app

    client = TestClient(app)
    headers = {'Authorization': f'Bearer {raw_key}', 'Idempotency-Key': 'refresh-1'}
    first = client.post('/api/jobs', headers=headers, json={'kind': 'crawl.refresh', 'payload': {'work_id': 'work-1'}})
    second = client.post('/api/jobs', headers=headers, json={'kind': 'crawl.refresh', 'payload': {'work_id': 'work-1'}})

    assert first.status_code == second.status_code == 200
    assert first.json()['data']['job_id'] == second.json()['data']['job_id']
    status = client.get(f"/api/jobs/{first.json()['data']['job_id']}", headers={'Authorization': f'Bearer {raw_key}'})
    assert status.status_code == 200
    assert status.json()['data']['status'] == 'queued'
    assert [event['type'] for event in status.json()['data']['events']] == ['queued']


def test_job_events_require_events_read_capability(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'client-job-events-permission.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import generate_api_key, hash_api_key
    from app.domain.entities.auth import ApiKey
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    raw_key = generate_api_key()
    asyncio.run(SQLiteAuthRepository().save_api_key(ApiKey(name='submit-only', key_hash=hash_api_key(raw_key), permissions=['jobs.submit'])))

    from app.main import app

    client = TestClient(app)
    headers = {'Authorization': f'Bearer {raw_key}'}
    created = client.post('/api/jobs', headers=headers, json={'kind': 'crawl.refresh'})
    response = client.get(f"/api/jobs/{created.json()['data']['job_id']}", headers=headers)

    assert response.status_code == 403
    assert response.json()['code'] == 'AUTHORIZATION_ERROR'


def test_api_key_cannot_read_another_key_job(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'client-job-isolation.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import generate_api_key, hash_api_key
    from app.domain.entities.auth import ApiKey
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    owner_key = generate_api_key()
    other_key = generate_api_key()
    repository = SQLiteAuthRepository()
    asyncio.run(repository.save_api_key(ApiKey(name='owner', key_hash=hash_api_key(owner_key), permissions=['jobs.submit'])))
    asyncio.run(repository.save_api_key(ApiKey(name='other', key_hash=hash_api_key(other_key), permissions=['read.work'])))

    from app.main import app

    client = TestClient(app)
    created = client.post(
        '/api/jobs',
        headers={'Authorization': f'Bearer {owner_key}'},
        json={'kind': 'crawl.refresh', 'payload': {'work_id': 'work-1'}},
    )

    assert created.status_code == 200
    response = client.get(
        f"/api/jobs/{created.json()['data']['job_id']}",
        headers={'Authorization': f'Bearer {other_key}'},
    )

    assert response.status_code == 404
    assert response.json()['detail'] == 'Job not found'
