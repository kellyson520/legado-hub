from fastapi.testclient import TestClient


def test_health_requires_auth_except_status(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "health.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/health").status_code == 401

    token = create_access_token({"sub": "1", "permissions": ["health.check"], "sid": "health-1"})
    assert client.get("/api/health", headers={"Authorization": f"Bearer {token}"}).status_code == 200
