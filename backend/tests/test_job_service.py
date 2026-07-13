from datetime import datetime, timedelta, timezone

import pytest


def test_expired_lease_is_reclaimed_once(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'jobs.sqlite3'))

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    job = service.enqueue(kind='crawl.refresh', tenant_id='tenant-1', payload={'work_id': 'work-1'}, idempotency_key='key-1')

    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    first = service.lease_next(worker_id='worker-a', now=now, lease_seconds=60)
    second = service.lease_next(worker_id='worker-b', now=now + timedelta(seconds=61), lease_seconds=60)

    assert first is not None and first.id == job.id
    assert second is not None and second.id == job.id
    assert second.attempt_count == 2


def test_idempotency_key_returns_original_job(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'jobs-idempotency.sqlite3'))

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    first = service.enqueue(kind='source.build', tenant_id='tenant-1', payload={'url': 'https://example.test'}, idempotency_key='same-input')
    second = service.enqueue(kind='source.build', tenant_id='tenant-1', payload={'url': 'https://example.test'}, idempotency_key='same-input')

    assert first.id == second.id


def test_failed_job_requeues_then_moves_to_dead_letter(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'jobs-failure.sqlite3'))

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    job = service.enqueue(kind='source.build', tenant_id='tenant-1', payload={})
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    leased = service.lease_next(worker_id='worker-a', now=now)
    retried = service.fail(
        leased.id,
        error='temporary failure',
        worker_id='worker-a',
        lease_token=leased.lease_token,
        max_attempts=2,
        now=now,
    )
    assert retried.status == 'queued'

    leased_again = service.lease_next(worker_id='worker-b', now=now + timedelta(seconds=30))
    dead_letter = service.fail(
        leased_again.id,
        error='permanent failure',
        worker_id='worker-b',
        lease_token=leased_again.lease_token,
        max_attempts=2,
        now=now + timedelta(seconds=30),
    )

    assert dead_letter.id == job.id
    assert dead_letter.status == 'dead_letter'


def test_failed_job_waits_for_backoff_before_it_can_be_leased_again(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'jobs-backoff.sqlite3'))

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    service.enqueue(kind='source.build', tenant_id='tenant-1', payload={})
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    leased = service.lease_next(worker_id='worker-a', now=now)
    retried = service.fail(
        leased.id,
        error='temporary failure',
        worker_id='worker-a',
        lease_token=leased.lease_token,
        now=now,
    )

    assert retried.status == 'queued'
    assert retried.available_at == now + timedelta(seconds=30)
    assert service.lease_next(worker_id='worker-b', now=now + timedelta(seconds=29)) is None
    assert service.lease_next(worker_id='worker-b', now=now + timedelta(seconds=30)).id == leased.id


def test_job_lifecycle_is_recorded_as_an_immutable_tenant_scoped_timeline(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'job-events.sqlite3'))

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    job = service.enqueue(kind='source.build', tenant_id='tenant-1', payload={})
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    leased = service.lease_next(worker_id='worker-a', now=now)
    service.fail(
        job.id,
        error='temporary failure',
        worker_id='worker-a',
        lease_token=leased.lease_token,
        now=now,
    )

    events = service.list_events(job.id, tenant_id='tenant-1')

    assert [event.event_type for event in events] == ['queued', 'leased', 'retrying']
    assert events[-1].detail['error'] == 'temporary failure'
    assert service.list_events(job.id, tenant_id='tenant-2') is None


def test_database_rejects_duplicate_tenant_idempotency_keys(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'jobs-idempotency-constraint.sqlite3'))

    from app.database import SessionLocal
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.schema import JobModel
    from sqlalchemy.exc import IntegrityError

    bootstrap_sqlite()
    db = SessionLocal()
    try:
        db.add(JobModel(id='job-a', kind='source.build', tenant_id='tenant-1', idempotency_key='same-key'))
        db.commit()
        db.add(JobModel(id='job-b', kind='source.build', tenant_id='tenant-1', idempotency_key='same-key'))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_only_the_worker_holding_a_live_lease_can_finish_a_job(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'jobs-lease-owner.sqlite3'))

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    job = service.enqueue(kind='source.build', tenant_id='tenant-1', payload={})
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    lease = service.lease_next(worker_id='worker-a', now=now)

    with pytest.raises(PermissionError):
        service.complete(job.id, worker_id='worker-b', lease_token=lease.lease_token, now=now)

    assert service.get(job.id, tenant_id='tenant-1').status == 'leased'
    assert service.complete(job.id, worker_id='worker-a', lease_token=lease.lease_token, now=now).status == 'succeeded'


def test_expired_lease_cannot_finish_a_new_lease_held_by_the_same_worker(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'jobs-lease-token.sqlite3'))

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    job = service.enqueue(kind='source.build', tenant_id='tenant-1', payload={})
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    first_lease = service.lease_next(worker_id='worker-a', now=now)
    second_lease = service.lease_next(worker_id='worker-a', now=now + timedelta(seconds=61))

    with pytest.raises(PermissionError):
        service.complete(
            job.id,
            worker_id='worker-a',
            lease_token=first_lease.lease_token,
            now=now + timedelta(seconds=62),
        )

    assert service.complete(
        job.id,
        worker_id='worker-a',
        lease_token=second_lease.lease_token,
        now=now + timedelta(seconds=62),
    ).status == 'succeeded'


def test_job_migration_reports_existing_duplicate_idempotency_keys(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'jobs-duplicate-migration.sqlite3'))

    from app.database import Base, SessionLocal, engine
    from app.infrastructure.persistence.sqlite.bootstrap import _ensure_sqlite_job_columns
    from app.infrastructure.persistence.sqlite.schema import JobModel

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add_all(
            [
                JobModel(id='job-a', kind='source.build', tenant_id='tenant-1', idempotency_key='same-key'),
                JobModel(id='job-b', kind='source.build', tenant_id='tenant-1', idempotency_key='same-key'),
            ]
        )
        db.commit()
    finally:
        db.close()

    with pytest.raises(RuntimeError, match='duplicate idempotency keys'):
        _ensure_sqlite_job_columns()


def test_live_lease_can_be_extended_by_its_current_token_holder(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'jobs-lease-renewal.sqlite3'))

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    service.enqueue(kind='source.build', tenant_id='tenant-1', payload={})
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    lease = service.lease_next(worker_id='worker-a', now=now, lease_seconds=60)

    renewed = service.renew_lease(
        lease.id,
        worker_id='worker-a',
        lease_token=lease.lease_token,
        now=now + timedelta(seconds=30),
        lease_seconds=60,
    )

    assert renewed.lease_expires_at == now + timedelta(seconds=90)
    assert service.lease_next(worker_id='worker-b', now=now + timedelta(seconds=61)) is None
