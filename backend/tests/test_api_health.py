from fastapi.testclient import TestClient


def test_health_requires_auth_except_status(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "health.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    status_response = client.get("/api/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["success"] is True
    assert status_payload["code"] == "OK"
    assert status_payload["meta"] == {}
    assert status_payload["trace_id"] is None

    root_response = client.get("/")
    assert root_response.status_code == 200
    root_payload = root_response.json()
    assert root_payload["success"] is True
    assert root_payload["code"] == "OK"
    assert root_payload["meta"] == {}
    assert root_payload["trace_id"] is None

    assert client.get("/api/health").status_code == 401

    token = create_access_token({"sub": "1", "permissions": ["health.check"], "sid": "health-1"})
    assert client.get("/api/health", headers={"Authorization": f"Bearer {token}"}).status_code == 200
