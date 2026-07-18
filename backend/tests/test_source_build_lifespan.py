from fastapi.testclient import TestClient


async def test_app_lifespan_rehydrates_published_runtime_book_source(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'runtime-source-rehydration.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')
    monkeypatch.setenv('EVENT_DELIVERY_WORKER_ENABLED', 'false')
    monkeypatch.setenv('SOURCE_BUILD_WORKER_ENABLED', 'false')

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_repo_impl import SQLiteSourceRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    source_repo = SQLiteSourceRepository()
    published = runtime_repo.create_candidate_version(
        'book',
        'https://lifespan.example.test/books',
        {
            'bookSourceName': '启动重建书源',
            'bookSourceUrl': 'https://lifespan.example.test/books',
            'ruleSearch': {'bookList': '.book'},
        },
        '7',
    )
    runtime_repo.update_version_status(published.id, 'published')
    _, total_before = await source_repo.list_book_sources(page=1, page_size=10)
    assert total_before == 0

    from app.main import app

    with TestClient(app) as client:
        assert client.get('/api/status').status_code == 200

    legacy_sources, total_after = await source_repo.list_book_sources(page=1, page_size=10)
    assert total_after == 1
    assert legacy_sources[0]['bookSourceName'] == '启动重建书源'
    assert legacy_sources[0]['bookSourceUrl'] == 'https://lifespan.example.test/books'


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

    calls: list[object] = []

    class RuntimeService:
        async def register_published_book_sources(self) -> None:
            calls.append('runtime_sources_registered')

    async def fake_run_source_build_job(limit: int = 1) -> dict:
        calls.append(('source_build_worker', limit))
        return {'processed': 0, 'jobs': []}

    monkeypatch.setattr(app_main, 'build_source_runtime_service', lambda: RuntimeService(), raising=False)
    monkeypatch.setattr(app_main, 'run_source_build_job', fake_run_source_build_job)

    with TestClient(app) as client:
        response = client.get('/api/status')
        assert response.status_code == 200

    assert calls[0] == 'runtime_sources_registered'
    assert ('source_build_worker', 2) in calls


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


def test_app_lifespan_starts_and_stops_scheduler_outside_test_environment(monkeypatch, tmp_path):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'scheduler-lifespan.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.main import app
    import app.main as app_main

    class RuntimeService:
        async def register_published_book_sources(self) -> None:
            return None

    calls: list[str] = []
    monkeypatch.setattr(app_main.settings, 'ENV', 'dev')
    monkeypatch.setattr(app_main.settings, 'EVENT_DELIVERY_WORKER_ENABLED', False)
    monkeypatch.setattr(app_main.settings, 'SOURCE_BUILD_WORKER_ENABLED', False)
    monkeypatch.setattr(app_main, 'build_source_runtime_service', lambda: RuntimeService())
    monkeypatch.setattr(app_main, 'start_scheduler', lambda: calls.append('start'), raising=False)
    monkeypatch.setattr(app_main, 'stop_scheduler', lambda: calls.append('stop'), raising=False)

    with TestClient(app) as client:
        assert client.get('/api/status').status_code == 200

    assert calls == ['start', 'stop']
