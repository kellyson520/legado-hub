from fastapi.testclient import TestClient


def test_settings_default_to_project_local_sqlite(monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.config import Settings

    settings = Settings(_env_file=None)
    assert settings.DB_PATH.endswith("backend/data/legado_hub.sqlite3")
    assert settings.SECRET_KEY
    assert settings.ENV in {"dev", "test", "prod"}


def test_development_settings_generate_a_secret_when_environment_is_empty(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    assert len(settings.SECRET_KEY) >= 16


def test_root_no_longer_points_to_container_only_index(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.config import settings

    monkeypatch.setattr(settings, "APP_NAME", "LegadoHub API")

    from app.main import app

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["data"]["service"] == "LegadoHub API"


def test_status_is_the_only_public_baseline(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.main import app

    client = TestClient(app)
    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["success"] is True

    protected = client.get("/api/dashboard")
    assert protected.status_code in {401, 403, 404}


def test_cached_sqlite_bootstrap_runs_once_per_engine(monkeypatch):
    from app.infrastructure.persistence.sqlite import bootstrap as bootstrap_module

    calls = 0

    def fake_bootstrap():
        nonlocal calls
        calls += 1

    monkeypatch.setattr(bootstrap_module, 'bootstrap_sqlite', fake_bootstrap)
    monkeypatch.setattr(bootstrap_module, '_bootstrapped_engine_url', None)

    bootstrap_module.ensure_sqlite_bootstrap()
    bootstrap_module.ensure_sqlite_bootstrap()

    assert calls == 1


def test_direct_sqlite_bootstrap_marks_the_active_engine(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "bootstrap-marker.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.sqlite import bootstrap as bootstrap_module

    bootstrap_module._bootstrapped_engine_url = None
    bootstrap_module.bootstrap_sqlite()
    first_marker = bootstrap_module._bootstrapped_engine_url
    bootstrap_module.ensure_sqlite_bootstrap()

    assert first_marker == str(bootstrap_module.engine.url)
    assert bootstrap_module._bootstrapped_engine_url == first_marker
