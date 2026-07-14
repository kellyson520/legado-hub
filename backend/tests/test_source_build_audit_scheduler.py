import pytest
import threading


def _configure_database(monkeypatch, tmp_path, name: str) -> None:
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / name))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')


@pytest.mark.asyncio
async def test_run_source_build_job_returns_passed_audit_result_for_regular_build(monkeypatch, tmp_path):
    _configure_database(monkeypatch, tmp_path, 'source-build-audit-scheduler.sqlite3')

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence import factory
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.tasks.scheduler import run_source_build_job

    bootstrap_sqlite()
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build',
        tenant_id='system',
        payload={'source_version_id': 'candidate-1', 'source_audit_attempt': 9},
    )

    class FakeBuildRuntime:
        def __init__(self):
            self.handled_job_ids = []

        def handle_job(self, handled_job):
            self.handled_job_ids.append(handled_job.id)
            return {'source_version_id': handled_job.payload['source_version_id'], 'decision': 'canary'}

    class FakeAuditService:
        def __init__(self, runtime):
            self.runtime = runtime
            self.calls = []

        def audit_blocking(self, source_version_id, *, completed_repair_attempt=None):
            assert self.runtime.handled_job_ids == [job.id]
            self.calls.append((source_version_id, completed_repair_attempt))
            return {'source_version_id': source_version_id, 'status': 'passed', 'score': 100}

    runtime = FakeBuildRuntime()
    audit = FakeAuditService(runtime)
    monkeypatch.setattr(factory, 'build_source_build_runtime_service', lambda: runtime)
    monkeypatch.setattr(factory, 'build_source_build_audit_service', lambda: audit, raising=False)

    result = await run_source_build_job(limit=1)

    assert result['processed'] == 1
    assert result['jobs'] == [
        {
            'job_id': job.id,
            'status': 'succeeded',
            'build_result': {'source_version_id': 'candidate-1', 'decision': 'canary'},
            'audit_result': {'source_version_id': 'candidate-1', 'status': 'passed', 'score': 100},
        }
    ]
    assert audit.calls == [('candidate-1', None)]


@pytest.mark.asyncio
async def test_run_source_build_job_passes_completed_repair_attempt_to_audit(monkeypatch, tmp_path):
    _configure_database(monkeypatch, tmp_path, 'source-build-audit-repair-scheduler.sqlite3')

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence import factory
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.tasks.scheduler import run_source_build_job

    bootstrap_sqlite()
    JobService(SQLiteJobRepository()).enqueue(
        kind='source.build',
        tenant_id='system',
        payload={
            'source_version_id': 'candidate-1',
            'trigger': 'source_audit_repair',
            'source_audit_attempt': 2,
        },
    )

    class FakeBuildRuntime:
        def handle_job(self, handled_job):
            return {'source_version_id': handled_job.payload['source_version_id']}

    class FakeAuditService:
        def __init__(self):
            self.calls = []

        def audit_blocking(self, source_version_id, *, completed_repair_attempt=None):
            self.calls.append((source_version_id, completed_repair_attempt))
            return {'source_version_id': source_version_id, 'status': 'passed'}

    audit = FakeAuditService()
    monkeypatch.setattr(factory, 'build_source_build_runtime_service', FakeBuildRuntime)
    monkeypatch.setattr(factory, 'build_source_build_audit_service', lambda: audit, raising=False)

    await run_source_build_job(limit=1)

    assert audit.calls == [('candidate-1', 2)]


@pytest.mark.asyncio
async def test_run_source_build_job_retries_when_audit_recovery_fails(monkeypatch, tmp_path):
    _configure_database(monkeypatch, tmp_path, 'source-build-audit-retry-scheduler.sqlite3')

    from app.application.services.job_service import JobService
    from app.application.services.source_build_audit_service import SourceAuditRecoveryError
    from app.infrastructure.persistence import factory
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository
    from app.tasks.scheduler import run_source_build_job

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    runtime_repo = SQLiteSourceRuntimeRepository()
    version = runtime_repo.create_candidate_version(
        source_type='book',
        source_id='https://example.test/recovery',
        payload={'source_audit': {'status': 'pending', 'attempt': 0}},
        created_by='system',
    )
    job = service.enqueue(
        kind='source.build',
        tenant_id='system',
        payload={'source_version_id': version.id},
    )

    class FakeBuildRuntime:
        def handle_job(self, handled_job):
            return {'source_version_id': handled_job.payload['source_version_id']}

    class RecoveringAuditService:
        def audit_blocking(self, source_version_id, *, completed_repair_attempt=None):
            runtime_repo.update_version_payload(
                source_version_id,
                {
                    'source_audit': {
                        'status': 'retry_pending',
                        'attempt': 1,
                        'test_run_pending': True,
                    }
                },
            )
            raise SourceAuditRecoveryError('source audit checkpoint requires recovery')

    monkeypatch.setattr(factory, 'build_source_build_runtime_service', FakeBuildRuntime)
    monkeypatch.setattr(factory, 'build_source_build_audit_service', RecoveringAuditService, raising=False)

    result = await run_source_build_job(limit=1)
    stored = service.get(job.id, tenant_id='system')
    stored_version = runtime_repo.get_version(version.id)

    assert result['jobs'][0]['status'] == 'queued'
    assert stored is not None
    assert stored.status == 'queued'
    assert stored.attempt_count == 1
    assert stored.last_error == 'source audit checkpoint requires recovery'
    assert stored_version is not None
    assert stored_version.payload['source_audit'] == {
        'status': 'retry_pending',
        'attempt': 1,
        'test_run_pending': True,
    }


@pytest.mark.asyncio
async def test_run_source_build_job_does_not_audit_when_runtime_fails(monkeypatch, tmp_path):
    _configure_database(monkeypatch, tmp_path, 'source-build-audit-runtime-failure.sqlite3')

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence import factory
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.tasks.scheduler import run_source_build_job

    bootstrap_sqlite()
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build',
        tenant_id='system',
        payload={'source_version_id': 'candidate-1'},
    )

    class FailingBuildRuntime:
        def handle_job(self, handled_job):
            raise RuntimeError('source build failed')

    class FakeAuditService:
        def __init__(self):
            self.calls = []

        def audit_blocking(self, source_version_id, *, completed_repair_attempt=None):
            self.calls.append((source_version_id, completed_repair_attempt))
            return {'status': 'passed'}

    audit = FakeAuditService()
    monkeypatch.setattr(factory, 'build_source_build_runtime_service', FailingBuildRuntime)
    monkeypatch.setattr(factory, 'build_source_build_audit_service', lambda: audit, raising=False)

    result = await run_source_build_job(limit=1)

    assert result['jobs'][0]['job_id'] == job.id
    assert result['jobs'][0]['status'] == 'queued'
    assert audit.calls == []


@pytest.mark.asyncio
async def test_run_source_build_job_executes_build_and_audit_off_event_loop_thread(monkeypatch, tmp_path):
    _configure_database(monkeypatch, tmp_path, 'source-build-audit-worker-thread.sqlite3')

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence import factory
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.tasks.scheduler import run_source_build_job

    bootstrap_sqlite()
    JobService(SQLiteJobRepository()).enqueue(
        kind='source.build',
        tenant_id='system',
        payload={'source_version_id': 'candidate-1'},
    )
    event_loop_thread_id = threading.get_ident()

    class FakeBuildRuntime:
        def __init__(self):
            self.thread_id = None

        def handle_job(self, handled_job):
            self.thread_id = threading.get_ident()
            return {'source_version_id': handled_job.payload['source_version_id']}

    class FakeAuditService:
        def __init__(self):
            self.thread_id = None

        def audit_blocking(self, source_version_id, *, completed_repair_attempt=None):
            self.thread_id = threading.get_ident()
            return {'source_version_id': source_version_id, 'status': 'passed'}

    runtime = FakeBuildRuntime()
    audit = FakeAuditService()
    monkeypatch.setattr(factory, 'build_source_build_runtime_service', lambda: runtime)
    monkeypatch.setattr(factory, 'build_source_build_audit_service', lambda: audit, raising=False)

    result = await run_source_build_job(limit=1)

    assert result['jobs'][0]['status'] == 'succeeded'
    assert runtime.thread_id is not None
    assert runtime.thread_id != event_loop_thread_id
    assert audit.thread_id == runtime.thread_id
