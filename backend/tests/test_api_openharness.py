from fastapi.testclient import TestClient


def _payload():
    return {
        "protocol_version": "1.0.0",
        "request_id": "req-http-1",
        "correlation_id": "corr-http-1",
        "capabilities": {"openharness.ui.approval": True},
        "request": {
            "auth": {"tenant_id": "forged-tenant"},
            "context": {
                "session_id": "session-http-1",
                "user_intent": "hello",
            },
        },
    }


def test_openharness_endpoint_returns_raw_protocol_response(monkeypatch):
    from app.core.security import create_access_token
    from app.interfaces.http import harness as harness_router
    from app.main import app

    class FakeService:
        async def execute(self, request, *, tenant_id):
            from app.infrastructure.harness.openharness.models import (
                ActionDirective,
                OpenHarnessResponse,
                OpenHarnessResponseBody,
            )

            assert tenant_id == "user:7"
            return OpenHarnessResponse(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                response=OpenHarnessResponseBody(
                    status="success",
                    action_directives=[
                        ActionDirective(action_type="render_message", payload={"message": "hello"}),
                    ],
                ),
            )

    monkeypatch.setattr(harness_router, "build_openharness_service", lambda: FakeService())
    token = create_access_token({"sub": "7", "permissions": ["ai.run"], "roles": []})

    response = TestClient(app).post(
        "/api/harness/v1/execute",
        headers={"Authorization": f"Bearer {token}"},
        json=_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["protocol_version"] == "1.0.0"
    assert body["request_id"] == "req-http-1"
    assert body["response"]["action_directives"][0]["action_type"] == "render_message"
    assert "data" not in body


def test_openharness_endpoint_returns_protocol_error_for_unsupported_version():
    from app.core.security import create_access_token
    from app.main import app

    token = create_access_token({"sub": "7", "permissions": ["ai.run"], "roles": []})
    payload = _payload()
    payload["protocol_version"] = "2.0.0"

    response = TestClient(app).post(
        "/api/harness/v1/execute",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "req-http-1"
    assert body["response"]["status"] == "error"
    assert body["response"]["error"]["code"] == "protocol_version_unsupported"


def test_openharness_endpoint_requires_ai_permission():
    from app.core.security import create_access_token
    from app.main import app

    token = create_access_token({"sub": "7", "permissions": [], "roles": []})
    response = TestClient(app).post(
        "/api/harness/v1/execute",
        headers={"Authorization": f"Bearer {token}"},
        json=_payload(),
    )

    assert response.status_code == 403
