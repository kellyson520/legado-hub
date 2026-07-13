from fastapi.testclient import TestClient


def test_legacy_v0_surface_is_not_mounted_anymore(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.main import app

    client = TestClient(app)
    assert client.get("/api/sources/book").status_code == 404


def test_main_api_status_is_public(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.main import app

    client = TestClient(app)
    assert client.get("/api/status").status_code == 200
