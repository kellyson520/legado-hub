from fastapi.testclient import TestClient


def test_sources_are_protected_and_paginated_in_meta(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "sources.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    unauth = client.get("/api/sources/book_sources")
    assert unauth.status_code == 401

    token = create_access_token({"sub": "1", "permissions": ["book_sources.read"], "sid": "sources-1"})
    auth = client.get(
        "/api/sources/book_sources?page=1&page_size=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert auth.status_code == 200
    assert auth.json()["meta"] == {"page": 1, "page_size": 20, "total": 0, "total_pages": 0}
