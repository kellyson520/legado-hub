from fastapi.testclient import TestClient


def test_export_requires_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "dashboard.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    assert client.get("/api/export/book_sources").status_code == 401

    token = create_access_token(
        {"sub": "1", "permissions": ["dashboard.read", "export.read", "health.check"], "sid": "dash-1"}
    )
    dashboard = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert dashboard.status_code == 200
    assert {"book_sources", "rss_sources", "subscriptions", "filter_rules"} <= set(dashboard.json()["data"].keys())

    export = client.get("/api/export/book_sources", headers={"Authorization": f"Bearer {token}"})
    assert export.status_code == 200
    assert isinstance(export.json()["data"]["items"], list)

    health = client.get("/api/health", headers={"Authorization": f"Bearer {token}"})
    assert health.status_code == 200
