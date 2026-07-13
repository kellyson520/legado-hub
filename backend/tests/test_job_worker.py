from datetime import datetime, timezone
from threading import Event


def test_worker_completes_a_registered_job_handler(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'job-worker-success.sqlite3'))

    from app.application.services.job_service import JobService
    from app.application.services.job_worker import JobWorker
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    job = service.enqueue(kind='source.build', tenant_id='tenant-1', payload={'url': 'https://example.test'})
    handled = []
    worker = JobWorker(service, worker_id='worker-a', handlers={'source.build': lambda leased: handled.append(leased.id)})

    result = worker.run_once(now=datetime(2026, 7, 10, tzinfo=timezone.utc))

    assert result.id == job.id
    assert result.status == 'succeeded'
    assert handled == [job.id]
    assert [event.event_type for event in service.list_events(job.id, tenant_id='tenant-1')] == ['queued', 'leased', 'succeeded']


def test_worker_retries_a_handler_exception_with_job_backoff(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'job-worker-failure.sqlite3'))

    from app.application.services.job_service import JobService
    from app.application.services.job_worker import JobWorker
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    job = service.enqueue(kind='source.build', tenant_id='tenant-1', payload={})

    def fail_handler(_job):
        raise RuntimeError('upstream unavailable')

    worker = JobWorker(service, worker_id='worker-a', handlers={'source.build': fail_handler})
    result = worker.run_once(now=datetime(2026, 7, 10, tzinfo=timezone.utc))

    assert result.id == job.id
    assert result.status == 'queued'
    assert result.last_error == 'upstream unavailable'


def test_worker_retries_an_unregistered_job_kind_without_executing_it(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'job-worker-unregistered.sqlite3'))

    from app.application.services.job_service import JobService
    from app.application.services.job_worker import JobWorker
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    job = service.enqueue(kind='unregistered.kind', tenant_id='tenant-1', payload={})
    worker = JobWorker(service, worker_id='worker-a', handlers={})

    result = worker.run_once(now=datetime(2026, 7, 10, tzinfo=timezone.utc))

    assert result.status == 'queued'
    assert result.last_error == 'No handler registered for job kind: unregistered.kind'
    assert [event.event_type for event in service.list_events(job.id, tenant_id='tenant-1')] == ['queued', 'leased', 'retrying']


def test_worker_renews_the_lease_while_a_handler_is_running(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'job-worker-heartbeat.sqlite3'))

    from app.application.services.job_service import JobService
    from app.application.services.job_worker import JobWorker
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    job = service.enqueue(kind='source.build', tenant_id='tenant-1', payload={})
    start = datetime(2026, 7, 10, tzinfo=timezone.utc)
    heartbeat_seen = Event()
    clock_values = iter([start, start.replace(minute=0, second=30), start.replace(minute=1, second=1)])

    def clock():
        value = next(clock_values)
        if value.second == 30:
            heartbeat_seen.set()
        return value

    def long_running_handler(_job):
        assert heartbeat_seen.wait(timeout=1)

    worker = JobWorker(
        service,
        worker_id='worker-a',
        handlers={'source.build': long_running_handler},
        heartbeat_seconds=0.01,
        clock=clock,
    )

    result = worker.run_once()

    assert result.id == job.id
    assert result.status == 'succeeded'
    assert [event.event_type for event in service.list_events(job.id, tenant_id='tenant-1')] == [
        'queued',
        'leased',
        'lease_renewed',
        'succeeded',
    ]


def test_worker_heartbeat_uses_a_live_clock_when_initial_lease_time_is_supplied(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'job-worker-explicit-time-heartbeat.sqlite3'))

    from app.application.services.job_service import JobService
    from app.application.services.job_worker import JobWorker
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository

    bootstrap_sqlite()
    service = JobService(SQLiteJobRepository())
    service.enqueue(kind='source.build', tenant_id='tenant-1', payload={})
    start = datetime(2026, 7, 10, tzinfo=timezone.utc)
    heartbeat_seen = Event()

    def clock():
        heartbeat_seen.set()
        return start.replace(second=30)

    def long_running_handler(_job):
        assert heartbeat_seen.wait(timeout=1)
        assert service.lease_next(worker_id='worker-b', now=start.replace(minute=1, second=1)) is None

    worker = JobWorker(
        service,
        worker_id='worker-a',
        handlers={'source.build': long_running_handler},
        heartbeat_seconds=0.01,
        clock=clock,
    )

    assert worker.run_once(now=start).status == 'succeeded'
