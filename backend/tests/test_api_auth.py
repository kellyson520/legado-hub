from fastapi.testclient import TestClient


def test_legacy_login_path_is_gone(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.main import app

    client = TestClient(app)
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123456"})
    assert response.status_code == 404
