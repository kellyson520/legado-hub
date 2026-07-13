import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def test_webhook_delivery_has_event_id_and_hmac_signature():
    from app.application.services.event_delivery_service import EventDeliveryService

    delivery = EventDeliveryService(signing_secret='unit-test-secret').prepare(
        event_type='chapter.ready',
        tenant_id='t1',
        payload={'chapter_id': 'c1'},
    )

    assert delivery.headers['X-Legado-Event-Id'] == delivery.event_id
    assert delivery.headers['X-Legado-Signature'].startswith('sha256=')
    assert json.loads(delivery.body)['payload']['chapter_id'] == 'c1'


def test_operations_jobs_endpoint_lists_jobs_for_console(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'events-jobs.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_job_service

    bootstrap_sqlite()
    build_job_service().enqueue(
        kind='crawl.refresh',
        tenant_id='tenant-console',
        payload={'work_id': 'w1'},
        idempotency_key='job-1',
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['system.jobs.manage']})
    response = TestClient(app).get('/api/events/jobs', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    assert response.json()['data'][0]['kind'] == 'crawl.refresh'
    assert response.json()['data'][0]['status'] == 'queued'


def test_webhook_enqueue_is_deduplicated_by_delivery_key(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'event-dedupe.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_event_delivery_service

    bootstrap_sqlite()
    service = build_event_delivery_service()

    first = service.enqueue_webhook(
        event_type='chapter.ready',
        tenant_id='tenant-1',
        payload={'chapter_id': 'c1'},
        target_url='https://callback.test/webhook',
        dedupe_key='chapter.ready:c1',
    )
    second = service.enqueue_webhook(
        event_type='chapter.ready',
        tenant_id='tenant-1',
        payload={'chapter_id': 'c1'},
        target_url='https://callback.test/webhook',
        dedupe_key='chapter.ready:c1',
    )

    assert first.event_id == second.event_id
    assert first.dedupe_key == second.dedupe_key == 'chapter.ready:c1'


def test_failed_delivery_records_retry_schedule_and_failure_history(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'event-retries.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_event_delivery_service

    bootstrap_sqlite()
    service = build_event_delivery_service()
    delivery = service.enqueue_webhook(
        event_type='chapter.ready',
        tenant_id='tenant-1',
        payload={'chapter_id': 'c1'},
        target_url='https://callback.test/webhook',
        dedupe_key='chapter.ready:c1',
    )

    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    first_retry = service.record_attempt(
        delivery.event_id,
        delivered=False,
        status_code=503,
        error_message='upstream unavailable',
        now=now,
        max_attempts=2,
    )
    final_state = service.record_attempt(
        delivery.event_id,
        delivered=False,
        status_code=503,
        error_message='still unavailable',
        now=now + timedelta(seconds=31),
        max_attempts=2,
    )

    history = service.list_attempts(delivery.event_id)

    assert first_retry.status == 'retrying'
    assert first_retry.next_attempt_at is not None
    assert first_retry.next_attempt_at > now
    assert final_state.status == 'failed'
    assert final_state.last_error == 'still unavailable'
    assert len(history) == 2
    assert history[0].error_message == 'upstream unavailable'
    assert history[1].error_message == 'still unavailable'


def test_dispatch_due_webhook_marks_delivery_delivered_and_records_attempt(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'event-dispatch.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_event_delivery_service

    bootstrap_sqlite()
    service = build_event_delivery_service()
    delivery = service.enqueue_webhook(
        event_type='chapter.ready',
        tenant_id='tenant-1',
        payload={'chapter_id': 'c1'},
        target_url='https://callback.test/webhook',
        dedupe_key='chapter.ready:c1',
    )

    dispatched = service.deliver_due_webhooks(
        now=datetime(2026, 7, 11, tzinfo=timezone.utc),
        sender=lambda queued: (202, None),
    )
    history = service.list_attempts(delivery.event_id)

    assert len(dispatched) == 1
    assert dispatched[0].event_id == delivery.event_id
    assert dispatched[0].status == 'delivered'
    assert dispatched[0].delivered_at is not None
    assert len(history) == 1
    assert history[0].delivered is True
    assert history[0].status_code == 202


def test_dispatch_due_webhook_skips_retry_before_next_attempt_at(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'event-dispatch-retry.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_event_delivery_service

    bootstrap_sqlite()
    service = build_event_delivery_service()
    delivery = service.enqueue_webhook(
        event_type='chapter.ready',
        tenant_id='tenant-1',
        payload={'chapter_id': 'c1'},
        target_url='https://callback.test/webhook',
        dedupe_key='chapter.ready:c1',
    )

    first_retry = service.record_attempt(
        delivery.event_id,
        delivered=False,
        status_code=503,
        error_message='upstream unavailable',
        now=datetime(2026, 7, 11, tzinfo=timezone.utc),
        max_attempts=3,
    )
    skipped = service.deliver_due_webhooks(
        now=datetime(2026, 7, 11, 0, 0, 5, tzinfo=timezone.utc),
        sender=lambda queued: (200, None),
    )
    delivered = service.deliver_due_webhooks(
        now=first_retry.next_attempt_at,
        sender=lambda queued: (200, None),
    )
    history = service.list_attempts(delivery.event_id)

    assert skipped == []
    assert len(delivered) == 1
    assert delivered[0].status == 'delivered'
    assert len(history) == 2
    assert history[0].error_message == 'upstream unavailable'
    assert history[1].delivered is True


def test_operations_deliveries_endpoints_list_delivery_state_and_attempts(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'events-deliveries.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_event_delivery_service

    bootstrap_sqlite()
    service = build_event_delivery_service()
    delivery = service.enqueue_webhook(
        event_type='chapter.ready',
        tenant_id='tenant-console',
        payload={'chapter_id': 'c1'},
        target_url='https://callback.test/webhook',
        dedupe_key='chapter.ready:c1',
    )
    service.record_attempt(
        delivery.event_id,
        delivered=False,
        status_code=503,
        error_message='upstream unavailable',
        now=datetime(2026, 7, 11, tzinfo=timezone.utc),
        max_attempts=3,
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['system.jobs.manage']})
    client = TestClient(app)
    deliveries = client.get('/api/events/deliveries', headers={'Authorization': f'Bearer {token}'})
    attempts = client.get(
        f'/api/events/deliveries/{delivery.event_id}/attempts',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert deliveries.status_code == 200
    assert deliveries.json()['data'][0]['event_id'] == delivery.event_id
    assert deliveries.json()['data'][0]['status'] == 'retrying'
    assert deliveries.json()['data'][0]['attempt_count'] == 1
    assert attempts.status_code == 200
    assert attempts.json()['data'][0]['error_message'] == 'upstream unavailable'


def test_operations_event_stream_replays_recent_delivery_events(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'events-stream.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_event_delivery_service

    bootstrap_sqlite()
    service = build_event_delivery_service()
    delivery = service.enqueue_webhook(
        event_type='chapter.ready',
        tenant_id='tenant-stream',
        payload={'chapter_id': 'c1'},
        target_url='https://callback.test/webhook',
        dedupe_key='chapter.ready:c1',
    )
    service.record_attempt(
        delivery.event_id,
        delivered=False,
        status_code=503,
        error_message='upstream unavailable',
        now=datetime(2026, 7, 11, tzinfo=timezone.utc),
        max_attempts=3,
    )

    from app.main import app

    token = create_access_token({'sub': '1', 'permissions': ['system.jobs.manage']})
    response = TestClient(app).get(
        '/api/events/stream?tenant_id=tenant-stream&once=true',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    assert 'event: event.delivery' in response.text
    assert '"tenant_id":"tenant-stream"' in response.text
    assert '"status":"retrying"' in response.text
