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
    assert created.json()["data"]["owner_scope"] == "user:1"
    assert client.get(f"/api/ai/conversations/{conversation_id}", headers={"Authorization": f"Bearer {other}"}).status_code == 404


def test_book_message_uses_the_bound_novel_agent(monkeypatch):
    from app.core.security import create_access_token
    from app.interfaces.http import ai as ai_router
    from app.main import app

    captured = {}

    class NovelAgent:
        pass

    novel_agent = NovelAgent()

    async def build_scoped_agent():
        captured["scoped_agent_called"] = True
        return novel_agent

    class Workspace:
        async def send_message(self, **kwargs):
            captured["message"] = kwargs
            return {"content": "已基于绑定书籍回答"}

    def build_workspace_service(**kwargs):
        captured["novel_agent_app"] = kwargs.get("novel_agent_app")
        return Workspace()

    monkeypatch.setattr(ai_router, "build_scoped_novel_agent_app_service", build_scoped_agent, raising=False)
    monkeypatch.setattr(ai_router, "build_ai_workspace_service", build_workspace_service)

    token = create_access_token({"sub": "1", "permissions": ["ai.run"], "roles": []})
    response = TestClient(app).post(
        "/api/ai/conversations/conversation-1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "content": "这本书讲述的什么故事",
            "mode": "chat",
            "entrypoint": "workspace",
            "book_id": 8,
        },
    )

    assert response.status_code == 200
    assert captured["scoped_agent_called"] is True
    assert captured["novel_agent_app"] is novel_agent
    assert captured["message"]["book_id"] == 8


def test_conversation_history_uses_lightweight_service(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "conversation-history.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.interfaces.http import ai as ai_router
    from app.main import app

    def fail_if_full_workspace_is_built(*args, **kwargs):
        raise AssertionError("conversation history must not build the full AI workspace")

    monkeypatch.setattr(ai_router, "build_ai_workspace_service", fail_if_full_workspace_is_built)

    token = create_access_token({"sub": "1", "permissions": ["ai.run"], "roles": []})
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)

    created = client.post("/api/ai/conversations", headers=headers, json={"title": "历史"})
    listed = client.get("/api/ai/conversations", headers=headers)
    conversation_id = created.json()["data"]["id"]
    loaded = client.get(f"/api/ai/conversations/{conversation_id}", headers=headers)

    assert created.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["data"][0]["id"] == conversation_id
    assert loaded.status_code == 200
    assert loaded.json()["data"]["id"] == conversation_id
