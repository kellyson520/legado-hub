from fastapi.testclient import TestClient


def test_app_lifespan_starts_event_delivery_worker_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'dev')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'event-lifespan.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')
    monkeypatch.setenv('EVENT_DELIVERY_WORKER_ENABLED', 'true')
    monkeypatch.setenv('EVENT_DELIVERY_POLL_SECONDS', '0.01')
    monkeypatch.setenv('EVENT_DELIVERY_BATCH_SIZE', '3')

    from app.main import app
    import app.main as app_main

    calls: list[int] = []

    async def fake_run_event_delivery_job(limit: int = 20) -> dict:
        calls.append(limit)
        return {'processed': 0, 'deliveries': []}

    monkeypatch.setattr(app_main, 'run_event_delivery_job', fake_run_event_delivery_job)

    with TestClient(app) as client:
        response = client.get('/api/status')
        assert response.status_code == 200

    assert calls
    assert calls[0] == 3
