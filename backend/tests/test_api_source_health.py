from fastapi.testclient import TestClient


def test_source_health_endpoints_require_auth_and_return_probe_payload(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    token = create_access_token(
        {"sub": "1", "permissions": ["book_sources.read", "book_sources.write"], "sid": "source-health-1"}
    )

    unauth = client.get("/api/source-health/book-sources")
    assert unauth.status_code == 401

    auth = client.get(
        "/api/source-health/book-sources",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert auth.status_code == 200
    assert auth.json()["success"] is True
