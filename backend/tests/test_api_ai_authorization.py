from fastapi.testclient import TestClient


class Workspace:
    async def decide_authorization(self, request_id, *, actor_id, conversation_id, decision, rbac_permissions=None):
        return {
            "authorization": {
                "id": request_id,
                "status": "consumed",
                "decision": decision,
                "conversation_id": conversation_id,
            },
            "message": {"id": "message-1", "content": "已恢复"},
        }

    def list_pending_authorizations(self, actor_id, conversation_id):
        return [{"id": "request-1", "status": "pending", "conversation_id": conversation_id}]

    def list_authorization_grants(self, actor_id, conversation_id=None):
        return [{"id": "grant-1", "scope": "conversation", "conversation_id": conversation_id}]

    async def revoke_authorization_grant(self, grant_id, *, actor_id):
        return {"id": grant_id, "scope": "conversation", "revoked_at": "2026-07-19T00:00:00"}


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ai-authorization-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.core.security import create_access_token
    import app.interfaces.http.ai as ai_router
    from app.main import app

    workspace = Workspace()
    monkeypatch.setattr(ai_router, "build_ai_workspace_service", lambda: workspace)
    monkeypatch.setattr(ai_router, "build_ai_conversation_service", lambda: workspace)
    client = TestClient(app)
    token = create_access_token({"sub": "7", "permissions": ["ai.run", "book_sources.read"], "roles": []})
    return client, {"Authorization": f"Bearer {token}"}


def test_decision_endpoint_returns_resumed_message(monkeypatch, tmp_path):
    client, headers = _client(monkeypatch, tmp_path)

    response = client.post(
        "/api/ai/conversations/conversation-1/authorization-requests/request-1/decision",
        headers=headers,
        json={"decision": "once"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["authorization"]["status"] == "consumed"
    assert response.json()["data"]["message"]["content"] == "已恢复"


def test_authorization_endpoints_require_ai_permission(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    from app.core.security import create_access_token

    denied = create_access_token({"sub": "7", "permissions": ["book_sources.read"], "roles": []})
    response = client.get(
        "/api/ai/conversations/conversation-1/authorization-requests",
        headers={"Authorization": f"Bearer {denied}"},
    )

    assert response.status_code == 403


def test_authorization_endpoints_validate_scope_and_support_listing_and_revoke(monkeypatch, tmp_path):
    client, headers = _client(monkeypatch, tmp_path)

    invalid = client.post(
        "/api/ai/conversations/conversation-1/authorization-requests/request-1/decision",
        headers=headers,
        json={"decision": "global"},
    )
    pending = client.get(
        "/api/ai/conversations/conversation-1/authorization-requests?status=pending",
        headers=headers,
    )
    grants = client.get("/api/ai/authorization-grants", headers=headers)
    revoked = client.post("/api/ai/authorization-grants/grant-1/revoke", headers=headers)

    assert invalid.status_code == 422
    assert pending.status_code == 200
    assert pending.json()["data"][0]["id"] == "request-1"
    assert grants.status_code == 200
    assert revoked.status_code == 200
