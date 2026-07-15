import asyncio

import pytest
from fastapi.testclient import TestClient


def test_manual_url_submission_creates_deduplicated_build_job(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-source-build.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import generate_api_key, hash_api_key
    from app.domain.entities.auth import ApiKey
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    raw_key = generate_api_key()
    asyncio.run(
        SQLiteAuthRepository().save_api_key(
            ApiKey(name='source-builder', key_hash=hash_api_key(raw_key), permissions=['source.submit'])
        )
    )

    from app.main import app

    client = TestClient(app)
    payload = {'url': 'https://example.test/books/', 'keyword': 'sample'}
    headers = {'Authorization': f'Bearer {raw_key}'}
    first = client.post('/api/source-builds', json=payload, headers=headers)
    second = client.post('/api/source-builds', json=payload, headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()['data']['job_id'] == second.json()['data']['job_id']
    assert first.json()['data']['source_version_id'] == second.json()['data']['source_version_id']
    assert first.json()['data']['normalized_url'] == 'https://example.test/books'


def test_manual_url_submission_requires_source_submit_capability(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-source-build-permission.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import generate_api_key, hash_api_key
    from app.domain.entities.auth import ApiKey
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    raw_key = generate_api_key()
    asyncio.run(
        SQLiteAuthRepository().save_api_key(
            ApiKey(name='no-source-submit', key_hash=hash_api_key(raw_key), permissions=['jobs.submit'])
        )
    )

    from app.main import app

    response = TestClient(app).post(
        '/api/source-builds',
        json={'url': 'https://example.test/books/', 'keyword': 'sample'},
        headers={'Authorization': f'Bearer {raw_key}'},
    )

    assert response.status_code == 403
    assert response.json()['message'] == 'Permission denied: source.submit'


def test_operations_source_builds_endpoint_lists_candidate_versions(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-source-build-operations.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_source_runtime_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = build_source_runtime_repository()
    audit_report = {
        'status': 'passed',
        'attempt': 1,
        'max_attempts': 5,
        'score': 100,
        'grade': 'A',
        'total_elapsed_ms': 480,
        'stages': {
            'search': {'status': 'ok', 'elapsed_ms': 120, 'hit_count': 1, 'title': 'Sample Book'},
            'toc': {'status': 'ok', 'elapsed_ms': 160, 'hit_count': 9, 'title': 'Chapter 1'},
            'content': {'status': 'ok', 'elapsed_ms': 200, 'content_length': 160, 'title': 'Chapter 1'},
        },
    }
    source_audit = {
        'status': 'passed',
        'attempt': 1,
        'max_attempts': 5,
        'score': 100,
        'grade': 'A',
        'report': audit_report,
    }
    version = repo.create_candidate_version(
        source_type='book',
        source_id='https://example.test/books',
        payload={
            'keyword': 'sample',
            'canonical_url': 'https://example.test/books',
            'source_audit': source_audit,
        },
        created_by='tenant-console',
    )
    repo.record_test_run(
        source_version_id=version.id,
        trigger='manual',
        score=88,
        grade='B',
        step_results={'search': {'passed': True, 'elapsed_ms': 120}},
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['book_sources.read']})
    response = TestClient(app).get('/api/events/source-builds', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    row = response.json()['data'][0]
    assert row['id'] == version.id
    assert row['source_id'] == 'https://example.test/books'
    assert row['payload']['keyword'] == 'sample'
    assert row['payload']['source_audit'] == source_audit
    assert row['latest_run']['grade'] == 'B'


def test_operations_source_builds_endpoint_includes_failed_terminal_audit_versions(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-source-build-terminal-audit.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_source_runtime_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    terminal_audit = {
        'status': 'failed',
        'attempt': 5,
        'max_attempts': 5,
        'score': 0,
        'grade': 'F',
        'report': {
            'status': 'failed',
            'reason': 'content parse failed',
            'total_elapsed_ms': 480,
            'stages': {
                'search': {'status': 'ok', 'elapsed_ms': 120, 'hit_count': 1, 'title': 'Sample Book'},
                'toc': {'status': 'ok', 'elapsed_ms': 160, 'hit_count': 9, 'title': 'Chapter 1'},
                'content': {'status': 'failed', 'elapsed_ms': 200, 'content_length': 0, 'title': 'Chapter 1'},
            },
        },
    }
    bootstrap_sqlite()
    repo = build_source_runtime_repository()
    candidate = repo.create_candidate_version(
        source_type='book',
        source_id='https://example.test/candidate',
        payload={'canonical_url': 'https://example.test/candidate'},
        created_by='tenant-console',
    )
    failed = repo.create_candidate_version(
        source_type='book',
        source_id='https://example.test/audit-failed',
        payload={
            'canonical_url': 'https://example.test/audit-failed',
            'source_audit': terminal_audit,
        },
        created_by='system',
    )
    repo.update_version_status(failed.id, 'failed')

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['book_sources.read']})
    response = TestClient(app).get('/api/events/source-builds', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    rows = response.json()['data']
    assert {row['id'] for row in rows} == {candidate.id, failed.id}
    assert len(rows) <= 50
    assert rows == sorted(rows, key=lambda row: (row['created_at'] or '', row['id']), reverse=True)
    failed_row = next(row for row in rows if row['id'] == failed.id)
    assert failed_row['status'] == 'failed'
    assert failed_row['payload']['source_audit'] == terminal_audit


def test_operations_source_builds_endpoint_exposes_autonomous_build_backflow(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-source-build-autonomous.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence.factory import build_source_build_runtime_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository
    from app.core.security import create_access_token

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    version = runtime_repo.create_candidate_version(
        source_type='book',
        source_id='https://example.test/books',
        payload={'canonical_url': 'https://example.test/books'},
        created_by='system',
    )
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build',
        tenant_id='system',
        payload={
            'url': 'https://example.test/books',
            'source_version_id': version.id,
            'site_profile': {
                'site_id': 'example.test',
                'dom_signatures': ['sig-1'],
                'template_patch': {'selector': '#book-list'},
                'fixture_coverage': 0.95,
                'confidence': 0.92,
                'risk_level': 'low',
            },
            'evidence': {
                'dom_signature': 'sig-1',
                'patch_candidate': {'selector': '#book-list'},
            },
            'fixture_validation_passed': True,
            'sample_validation_passed': True,
            'trigger': 'configured_catalog',
        },
    )
    build_source_build_runtime_service().handle_job(job)

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['book_sources.read']})
    response = TestClient(app).get('/api/events/source-builds', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    row = next(item for item in response.json()['data'] if item['id'] == version.id)
    assert row['payload']['autonomous_build']['decision'] == 'canary'
    assert row['payload']['autonomous_build']['agent_run_id']


def test_operations_source_builds_endpoint_exposes_probe_driven_autonomous_summary(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-source-build-probe.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.job_service import JobService
    from app.application.services.source_build_runtime_service import SourceBuildRuntimeService
    from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult
    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import (
        build_agent_runtime_service,
        build_source_build_agent,
    )
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    class FakeProbeService:
        async def probe_source(self, source, keyword_samples, probe_mode='full_chain'):
            return SourceProbeEvidence(
                source_id=source['id'],
                source_name=source.get('bookSourceName', ''),
                source_url=source.get('bookSourceUrl', ''),
                probe_mode=probe_mode,
                keyword=keyword_samples[0],
                search=StageProbeResult(
                    stage='search',
                    status='ok',
                    elapsed_ms=90,
                    request_preview='https://example.test/books/search?keyword=novel',
                    hit_count=1,
                    sample_title='Sample Book',
                    detail={
                        'top_hit': {
                            'name': 'Sample Book',
                            'bookUrl': 'https://example.test/books/1',
                        }
                    },
                ),
                toc=StageProbeResult(
                    stage='toc',
                    status='ok',
                    elapsed_ms=70,
                    hit_count=9,
                    sample_title='Chapter 1',
                    detail={
                        'first_chapter': {
                            'title': 'Chapter 1',
                            'url': 'https://example.test/books/1/1',
                        }
                    },
                ),
                content=StageProbeResult(
                    stage='content',
                    status='failed',
                    elapsed_ms=55,
                    error_message='content endpoint returned html',
                    sample_title='Chapter 1',
                    detail={'content_length': 0},
                ),
            )

        async def aclose(self):
            return None

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    version = runtime_repo.create_candidate_version(
        source_type='book',
        source_id='https://example.test/books',
        payload={'canonical_url': 'https://example.test/books'},
        created_by='system',
    )
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build',
        tenant_id='system',
        payload={
            'url': 'https://example.test/books',
            'source_version_id': version.id,
            'trigger': 'configured_catalog',
        },
    )
    SourceBuildRuntimeService(
        runtime_repo=runtime_repo,
        agent_runtime=build_agent_runtime_service(),
        build_agent=build_source_build_agent(),
        probe_factory=lambda: FakeProbeService(),
    ).handle_job(job)

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['book_sources.read']})
    response = TestClient(app).get('/api/events/source-builds', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    row = next(item for item in response.json()['data'] if item['id'] == version.id)
    assert row['payload']['autonomous_build']['inspection_mode'] == 'live_probe'
    assert row['payload']['autonomous_build']['probe']['search_status'] == 'ok'
    assert row['payload']['autonomous_build']['probe']['toc_status'] == 'ok'
    assert row['payload']['autonomous_build']['probe']['content_status'] == 'failed'
    assert row['payload']['autonomous_build']['probe']['failure_reason'] == 'content endpoint returned html'
    assert row['payload']['autonomous_build']['probe']['sample_title'] == 'Chapter 1'


def test_review_queue_includes_source_build_publish_candidates(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-source-build-review-queue.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_source_runtime_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = build_source_runtime_repository()
    version = repo.create_candidate_version(
        source_type='book',
        source_id='https://example.test/books',
        payload={'keyword': 'sample', 'canonical_url': 'https://example.test/books'},
        created_by='tenant-console',
    )
    repo.record_test_run(
        source_version_id=version.id,
        trigger='manual',
        score=96,
        grade='A',
        step_results={'search': {'passed': True, 'elapsed_ms': 120}},
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['agent_runs.read']})
    response = TestClient(app).get('/api/events/review-queue', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    row = next(item for item in response.json()['data'] if item['proposal_type'] == 'source_version_publish')
    assert row['item_type'] == 'source_version'
    assert row['object_name'] == 'https://example.test/books'
    assert row['summary'] == 'Publish source candidate (grade A)'


def test_review_queue_includes_persisted_source_review_items(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-source-review-queue.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_source_review_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    build_source_review_service().enqueue_build_escalation(
        source_version_id='source-version-1',
        source_url='https://example.test/books',
        reason_tags=['risk:high', 'budget:blocked'],
        model_context={'dom_signature': 'sig-9'},
        created_by='builder-1',
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['agent_runs.read']})
    response = TestClient(app).get('/api/events/review-queue', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    row = next(item for item in response.json()['data'] if item['item_type'] == 'source_review')
    assert row['proposal_type'] == 'build_escalation'
    assert row['object_name'] == 'https://example.test/books'
    assert row['evidence'] == 'risk:high, budget:blocked'
    assert row['created_by'] == 'builder-1'


def test_review_queue_exposes_terminal_source_audit_report(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-source-review-audit-failure.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_source_review_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    audit_report = {
        'status': 'failed',
        'attempt': 5,
        'max_attempts': 5,
        'score': 0,
        'grade': 'F',
        'reason': 'content parse failed',
        'total_elapsed_ms': 480,
        'stages': {
            'search': {'status': 'ok', 'elapsed_ms': 120, 'hit_count': 1, 'title': 'Sample Book'},
            'toc': {'status': 'ok', 'elapsed_ms': 160, 'hit_count': 9, 'title': 'Chapter 1'},
            'content': {'status': 'failed', 'elapsed_ms': 200, 'content_length': 0, 'title': 'Chapter 1'},
        },
    }
    bootstrap_sqlite()
    build_source_review_service().enqueue_audit_failure(
        source_version_id='source-version-audit-failed',
        source_url='https://example.test/audit-failed',
        audit_report=audit_report,
        created_by='system',
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['agent_runs.read']})
    response = TestClient(app).get('/api/events/review-queue', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    row = next(item for item in response.json()['data'] if item['proposal_type'] == 'source_audit_failed')
    assert row['item_type'] == 'source_review'
    assert row['evidence'] == 'content parse failed'
    assert row['payload']['audit_report'] == audit_report


@pytest.mark.parametrize(
    'audit',
    [
        {'status': 'pending', 'attempt': 0},
        {'status': 'failed', 'attempt': 5},
        {'status': 'passed', 'attempt': 1, 'test_run_pending': True},
    ],
    ids=['pending', 'failed', 'pending-checkpoint'],
)
def test_operations_review_queue_rejects_unsettled_source_audit(monkeypatch, tmp_path, audit):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / f"api-source-build-audit-{audit['status']}.sqlite3"))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_source_runtime_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = build_source_runtime_repository()
    version = repo.create_candidate_version(
        source_type='book',
        source_id='https://example.test/audit-blocked',
        payload={
            'keyword': 'sample',
            'canonical_url': 'https://example.test/audit-blocked',
            'source_audit': audit,
        },
        created_by='tenant-console',
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['agent_runs.write', 'engine.deploy']})
    response = TestClient(app).post(
        f'/api/events/review-queue/{version.id}/resolve',
        headers={'Authorization': f'Bearer {token}'},
        json={'item_type': 'source_version', 'action': 'publish'},
    )

    assert response.status_code == 422
    assert 'source audit' in response.json()['message'].lower()
    assert repo.get_version(version.id).status == 'candidate'


def test_operations_review_queue_can_publish_source_build_candidate_with_passed_audit_without_test_run(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-source-build-audit-passed.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_source_runtime_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = build_source_runtime_repository()
    version = repo.create_candidate_version(
        source_type='book',
        source_id='https://example.test/audit-passed',
        payload={
            'keyword': 'sample',
            'canonical_url': 'https://example.test/audit-passed',
            'source_audit': {'status': 'passed', 'attempt': 1},
        },
        created_by='tenant-console',
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['agent_runs.write', 'engine.deploy']})
    response = TestClient(app).post(
        f'/api/events/review-queue/{version.id}/resolve',
        headers={'Authorization': f'Bearer {token}'},
        json={'item_type': 'source_version', 'action': 'publish'},
    )

    assert response.status_code == 200
    assert response.json()['data']['status'] == 'published'


def test_operations_review_queue_can_publish_legacy_unmarked_source_build_candidate(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-source-build-review-resolve.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_source_runtime_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = build_source_runtime_repository()
    version = repo.create_candidate_version(
        source_type='book',
        source_id='https://example.test/books',
        payload={'keyword': 'sample', 'canonical_url': 'https://example.test/books'},
        created_by='tenant-console',
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['agent_runs.write', 'engine.deploy']})
    response = TestClient(app).post(
        f'/api/events/review-queue/{version.id}/resolve',
        headers={'Authorization': f'Bearer {token}'},
        json={'item_type': 'source_version', 'action': 'publish'},
    )

    assert response.status_code == 200
    assert response.json()['data']['queue_item_id'] == version.id
    assert response.json()['data']['item_type'] == 'source_version'
    assert response.json()['data']['status'] == 'published'


def test_operations_review_queue_can_resolve_source_review(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'api-source-review-resolve.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import (
        build_source_review_repository,
        build_source_review_service,
    )
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    review_item = build_source_review_service().enqueue_health_regression(
        source_version_id='source-version-1',
        source_url='https://example.test/books',
        decision={
            'action': 'rollback',
            'new_status': 'rolled_back',
            'reason': 'runtime health degraded',
            'allowed': False,
        },
        created_by='system',
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['agent_runs.write', 'book_sources.write']})
    response = TestClient(app).post(
        f'/api/events/review-queue/{review_item.id}/resolve',
        headers={'Authorization': f'Bearer {token}'},
        json={'item_type': 'source_review', 'action': 'resolve'},
    )

    assert response.status_code == 200
    assert response.json()['data']['queue_item_id'] == review_item.id
    assert response.json()['data']['item_type'] == 'source_review'
    assert response.json()['data']['status'] == 'resolved'
    stored = build_source_review_repository().get_item(review_item.id)
    assert stored is not None
    assert stored.status == 'resolved'
    assert stored.reviewed_by == '1'
