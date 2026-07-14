def test_manual_url_submission_creates_a_deduplicated_candidate_build(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build.sqlite3'))

    from app.application.services.source_build_service import SourceBuildService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository
    from app.application.services.job_service import JobService

    bootstrap_sqlite()
    service = SourceBuildService(
        JobService(SQLiteJobRepository()),
        SQLiteSourceRuntimeRepository(),
    )
    first = service.submit(tenant_id='tenant-1', url='https://Example.test/books/', keyword='sample')
    second = service.submit(tenant_id='tenant-1', url='https://example.test/books', keyword='sample')
    versions = SQLiteSourceRuntimeRepository().list_versions('book', 'https://example.test/books')

    assert first.job_id == second.job_id
    assert first.normalized_url == 'https://example.test/books'
    assert first.status == 'candidate'
    assert first.source_version_id == second.source_version_id
    assert first.source_version_status == 'candidate'
    assert len(versions) == 1
    assert versions[0].id == first.source_version_id
    assert versions[0].payload['keyword'] == 'sample'


def test_console_resubmit_after_completed_build_creates_fresh_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-retry.sqlite3'))

    from app.application.services.job_service import JobService
    from app.application.services.source_build_service import SourceBuildService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    jobs = JobService(SQLiteJobRepository())
    service = SourceBuildService(jobs, SQLiteSourceRuntimeRepository())
    first = service.submit(tenant_id='console:1', url='https://example.test/', keyword='novel')
    claimed = jobs.lease_next(worker_id='worker')
    jobs.complete(first.job_id, worker_id='worker', lease_token=claimed.lease_token)

    second = service.submit(tenant_id='console:1', url='https://example.test/', keyword='novel')

    assert second.job_id != first.job_id
    assert second.source_version_id != first.source_version_id


def test_health_regression_submission_creates_system_build_job_with_discovery_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-discovery.sqlite3'))

    from app.application.services.job_service import JobService
    from app.application.services.source_build_service import SourceBuildService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    service = SourceBuildService(
        JobService(SQLiteJobRepository()),
        SQLiteSourceRuntimeRepository(),
    )
    first = service.submit_discovery(
        tenant_id='system',
        url='https://Example.test/books/',
        baseline_source_version_id='baseline-1',
        reason='rollback',
        previous_status='published',
    )
    second = service.submit_discovery(
        tenant_id='system',
        url='https://example.test/books',
        baseline_source_version_id='baseline-1',
        reason='rollback',
        previous_status='published',
    )

    runtime_repo = SQLiteSourceRuntimeRepository()
    versions = runtime_repo.list_versions('book', 'https://example.test/books')
    discovery_version = next(version for version in versions if version.id == first.source_version_id)
    jobs = JobService(SQLiteJobRepository()).list_jobs()

    assert first.job_id == second.job_id
    assert first.source_version_id == second.source_version_id
    assert discovery_version.created_by == 'system'
    assert discovery_version.payload['discovery']['trigger'] == 'health_regression'
    assert discovery_version.payload['discovery']['reason'] == 'rollback'
    assert discovery_version.payload['discovery']['baseline_source_version_id'] == 'baseline-1'
    assert jobs[0].payload['trigger'] == 'health_regression'
    assert jobs[0].payload['baseline_source_version_id'] == 'baseline-1'


def test_catalog_discovery_submission_creates_system_candidate_with_catalog_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-catalog.sqlite3'))

    from app.application.services.job_service import JobService
    from app.application.services.source_build_service import SourceBuildService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    service = SourceBuildService(
        JobService(SQLiteJobRepository()),
        SQLiteSourceRuntimeRepository(),
    )
    first = service.submit_catalog_discovery(
        tenant_id='system',
        url='https://Example.test/catalog/',
        catalog_source_id=7,
        catalog_source_name='Catalog 7',
        catalog_source_group='seed',
    )
    second = service.submit_catalog_discovery(
        tenant_id='system',
        url='https://example.test/catalog',
        catalog_source_id=7,
        catalog_source_name='Catalog 7',
        catalog_source_group='seed',
    )

    runtime_repo = SQLiteSourceRuntimeRepository()
    versions = runtime_repo.list_versions('book', 'https://example.test/catalog')
    catalog_version = next(version for version in versions if version.id == first.source_version_id)
    jobs = JobService(SQLiteJobRepository()).list_jobs()

    assert first.job_id == second.job_id
    assert first.source_version_id == second.source_version_id
    assert catalog_version.payload['discovery']['trigger'] == 'configured_catalog'
    assert catalog_version.payload['discovery']['catalog_source_id'] == 7
    assert catalog_version.payload['discovery']['catalog_source_name'] == 'Catalog 7'
    assert jobs[0].payload['trigger'] == 'configured_catalog'
    assert jobs[0].payload['catalog_source_group'] == 'seed'


def test_submission_initializes_pending_source_audit_unless_explicitly_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-audit-pending.sqlite3'))

    from app.application.services.job_service import JobService
    from app.application.services.source_build_service import SourceBuildService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    runtime = SQLiteSourceRuntimeRepository()
    service = SourceBuildService(JobService(SQLiteJobRepository()), runtime)
    default = service.submit(tenant_id='tenant-1', url='https://example.test/default')
    overridden = service.submit(
        tenant_id='tenant-1',
        url='https://example.test/overridden',
        extra_payload={'source_audit': {'status': 'deferred', 'attempt': 3}},
    )

    default_version = runtime.get_version(default.source_version_id)
    overridden_version = runtime.get_version(overridden.source_version_id)

    assert default_version.payload['source_audit'] == {
        'status': 'pending',
        'attempt': 0,
        'max_attempts': 5,
        'history': [],
    }
    assert overridden_version.payload['source_audit'] == {'status': 'deferred', 'attempt': 3}


def test_audit_repair_enqueue_reuses_candidate_version_with_next_attempt_idempotency(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-audit-repair.sqlite3'))

    from app.application.services.job_service import JobService
    from app.application.services.source_build_service import SourceBuildService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    jobs = JobService(SQLiteJobRepository())
    service = SourceBuildService(jobs, SQLiteSourceRuntimeRepository())

    first = service.submit_audit_repair(
        tenant_id='tenant-1',
        source_version_id='candidate-1',
        url='https://example.test/books',
        keyword='sample',
        next_attempt=2,
    )
    second = service.submit_audit_repair(
        tenant_id='tenant-1',
        source_version_id='candidate-1',
        url='https://example.test/books',
        keyword='sample',
        next_attempt=2,
    )
    queued = jobs.list_jobs()

    assert first.id == second.id
    assert len(queued) == 1
    assert queued[0].kind == 'source.build'
    assert queued[0].payload == {
        'url': 'https://example.test/books',
        'keyword': 'sample',
        'source_version_id': 'candidate-1',
        'trigger': 'source_audit_repair',
        'source_audit_attempt': 2,
    }
    assert queued[0].idempotency_key == 'source.audit.repair:candidate-1:attempt-2'
