from fastapi.testclient import TestClient


def test_ai_workspace_requires_permission_and_enforces_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    denied = create_access_token({"sub": "1", "permissions": [], "roles": []})
    allowed = create_access_token({"sub": "1", "permissions": ["ai.run"], "roles": []})
    other = create_access_token({"sub": "2", "permissions": ["ai.run"], "roles": []})

    assert client.post("/api/ai/conversations", headers={"Authorization": f"Bearer {denied}"}, json={"title": "分析"}).status_code == 403
    created = client.post("/api/ai/conversations", headers={"Authorization": f"Bearer {allowed}"}, json={"title": "分析"})
    assert created.status_code == 200
    conversation_id = created.json()["data"]["id"]
    assert client.get(f"/api/ai/conversations/{conversation_id}", headers={"Authorization": f"Bearer {other}"}).status_code == 404
