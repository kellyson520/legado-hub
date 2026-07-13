from fastapi.testclient import TestClient


def test_ai_routes_live_under_main_api(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ai.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    token = create_access_token({"sub": "1", "permissions": ["ai.run"], "sid": "ai-legacy-1"})
    response = client.get("/api/ai/tasks", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
