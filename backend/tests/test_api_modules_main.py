from fastapi.testclient import TestClient


def test_engine_endpoints_are_permission_guarded(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "engine.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    assert client.post("/api/engine/generate", json={"url": "https://example.com"}).status_code == 401

    token = create_access_token({"sub": "1", "permissions": ["engine.generate"], "sid": "engine-1"})
    allowed = client.post(
        "/api/engine/generate",
        json={"url": "https://example.com", "sample": {"items": [{"name": "Book A"}]}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert allowed.status_code == 200


def test_translation_ai_novel_routes_exist_under_main_api(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "modules.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    token = create_access_token(
        {"sub": "1", "permissions": ["translation.run", "ai.run", "novel.manage"], "sid": "modules-1"}
    )
    for path in ("/api/translation/jobs", "/api/ai/tasks", "/api/novel/books"):
        response = client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["success"] is True
