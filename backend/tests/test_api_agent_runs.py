import asyncio

from fastapi.testclient import TestClient


def _create_api_key(repository, *, name: str, permissions: list[str]) -> str:
    from app.core.security import generate_api_key, hash_api_key
    from app.domain.entities.auth import ApiKey

    raw_key = generate_api_key()
    asyncio.run(
        repository.save_api_key(
            ApiKey(name=name, key_hash=hash_api_key(raw_key), permissions=permissions)
        )
    )
    return raw_key


def test_api_key_creates_and_reads_an_auditable_agent_run(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'agent-runs.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    key = _create_api_key(
        SQLiteAuthRepository(),
        name='agent-client',
        permissions=['agent_runs.read', 'agent_runs.write'],
    )

    from app.main import app

    client = TestClient(app)
    headers = {'Authorization': f'Bearer {key}'}
    created = client.post(
        '/api/agent-runs',
        headers=headers,
        json={'agent_kind': 'knowledge', 'input_payload': {'work_id': 'work-1'}},
    )

    assert created.status_code == 200
    assert created.json()['data']['agent_kind'] == 'knowledge'
    assert created.json()['data']['status'] == 'candidate'
    run_id = created.json()['data']['id']

    fetched = client.get(f'/api/agent-runs/{run_id}', headers=headers)

    assert fetched.status_code == 200
    assert fetched.json()['data']['id'] == run_id
    assert fetched.json()['data']['input_payload'] == {'work_id': 'work-1'}
    assert fetched.json()['data']['tool_history'] == []


def test_agent_run_creation_requires_write_capability(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'agent-runs-permission.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    key = _create_api_key(SQLiteAuthRepository(), name='read-only', permissions=['agent_runs.read'])

    from app.main import app

    response = TestClient(app).post(
        '/api/agent-runs',
        headers={'Authorization': f'Bearer {key}'},
        json={'agent_kind': 'knowledge'},
    )

    assert response.status_code == 403
    assert response.json()['code'] == 'AUTHORIZATION_ERROR'


def test_api_key_cannot_read_another_tenants_agent_run(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'agent-runs-isolation.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repository = SQLiteAuthRepository()
    owner_key = _create_api_key(
        repository,
        name='owner',
        permissions=['agent_runs.read', 'agent_runs.write'],
    )
    other_key = _create_api_key(repository, name='other', permissions=['agent_runs.read'])

    from app.main import app

    client = TestClient(app)
    created = client.post(
        '/api/agent-runs',
        headers={'Authorization': f'Bearer {owner_key}'},
        json={'agent_kind': 'source_build', 'input_payload': {'url': 'https://example.test'}},
    )
    response = client.get(
        f"/api/agent-runs/{created.json()['data']['id']}",
        headers={'Authorization': f'Bearer {other_key}'},
    )

    assert response.status_code == 404
    assert response.json()['detail'] == 'Agent run not found'


def test_operations_agent_runs_endpoint_lists_recent_runs_with_history_summary(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'agent-runs-operations.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_agent_runtime_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    service = build_agent_runtime_service()
    run = service.create_run(
        tenant_id='api-key:7',
        agent_kind='source_build',
        input_payload={'url': 'https://example.test/books'},
    )
    invocation = service.record_tool_invocation(
        run_id=run.id,
        tenant_id='api-key:7',
        tool_name='source.inspect',
        category='operate',
        arguments={'url': 'https://example.test/books'},
    )
    service.record_tool_result(
        invocation_id=invocation.id,
        tenant_id='api-key:7',
        status='accepted',
        data={'status': 'ok'},
    )
    service.record_tool_evidence(
        invocation_id=invocation.id,
        tenant_id='api-key:7',
        evidence_type='dom_snapshot',
        resource_id='snapshot-1',
        payload={'selector': '#book-list'},
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['agent_runs.read']})
    response = TestClient(app).get('/api/events/agent-runs', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    row = response.json()['data'][0]
    assert row['id'] == run.id
    assert row['tenant_id'] == 'api-key:7'
    assert row['tool_invocation_count'] == 1
    assert row['accepted_count'] == 1
    assert row['evidence_count'] == 1
    assert row['latest_tool_name'] == 'source.inspect'


def test_operations_agent_run_detail_endpoint_returns_tool_history(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'agent-runs-operations-detail.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_agent_runtime_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    service = build_agent_runtime_service()
    run = service.create_run(
        tenant_id='api-key:8',
        agent_kind='knowledge',
        input_payload={'work_id': 'work-1'},
    )
    invocation = service.record_tool_invocation(
        run_id=run.id,
        tenant_id='api-key:8',
        tool_name='knowledge.propose',
        category='propose',
        arguments={'work_id': 'work-1'},
    )
    service.record_tool_result(
        invocation_id=invocation.id,
        tenant_id='api-key:8',
        status='rejected',
        data={'reason': 'needs_more_evidence'},
        error_code='LOW_CONFIDENCE',
    )
    service.record_tool_evidence(
        invocation_id=invocation.id,
        tenant_id='api-key:8',
        evidence_type='chapter_excerpt',
        resource_id='chapter-1',
        payload={'quote': 'Lin trusts Mei'},
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['agent_runs.read']})
    response = TestClient(app).get(f'/api/events/agent-runs/{run.id}', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    data = response.json()['data']
    assert data['id'] == run.id
    assert data['tool_invocation_count'] == 1
    assert data['tool_history'][0]['tool_name'] == 'knowledge.propose'
    assert data['tool_history'][0]['result']['status'] == 'rejected'
    assert data['tool_history'][0]['result']['error_code'] == 'LOW_CONFIDENCE'
    assert data['tool_history'][0]['evidence'][0]['resource_id'] == 'chapter-1'
