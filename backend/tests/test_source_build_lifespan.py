from fastapi.testclient import TestClient


def test_app_lifespan_starts_source_build_worker_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'dev')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-lifespan.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')
    monkeypatch.setenv('SOURCE_BUILD_WORKER_ENABLED', 'true')
    monkeypatch.setenv('SOURCE_BUILD_POLL_SECONDS', '0.01')
    monkeypatch.setenv('SOURCE_BUILD_BATCH_SIZE', '2')
    monkeypatch.setenv('EVENT_DELIVERY_WORKER_ENABLED', 'false')

    from app.main import app
    import app.main as app_main

    calls: list[int] = []

    async def fake_run_source_build_job(limit: int = 1) -> dict:
        calls.append(limit)
        return {'processed': 0, 'jobs': []}

    monkeypatch.setattr(app_main, 'run_source_build_job', fake_run_source_build_job)

    with TestClient(app) as client:
        response = client.get('/api/status')
        assert response.status_code == 200

    assert calls
    assert calls[0] == 2


def test_app_lifespan_closes_interactive_browser_supervisor_on_shutdown(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'interactive-browser-lifespan.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.main import app
    import app.main as app_main

    calls = []
    to_thread_calls = []

    def close_interactive_browser_supervisor():
        calls.append('closed')

    async def run_close_off_loop(func):
        to_thread_calls.append(func)
        func()

    monkeypatch.setattr(
        app_main,
        'close_interactive_browser_supervisor',
        close_interactive_browser_supervisor,
        raising=False,
    )
    monkeypatch.setattr(app_main.asyncio, 'to_thread', run_close_off_loop)

    with TestClient(app) as client:
        assert client.get('/api/status').status_code == 200

    assert calls == ['closed']
    assert to_thread_calls == [close_interactive_browser_supervisor]
