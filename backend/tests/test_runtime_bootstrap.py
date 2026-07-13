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
