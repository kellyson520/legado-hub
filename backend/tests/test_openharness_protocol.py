import pytest


def _request(**overrides):
    request = {
        "protocol_version": "1.0.0",
        "request_id": "req-1",
        "correlation_id": "corr-1",
        "capabilities": {"openharness.ui.approval": True},
        "request": {
            "auth": {"tenant_id": "body-tenant", "credential_ref": "opaque-ref"},
            "context": {
                "session_id": "session-1",
                "conversation_id": "conversation-1",
                "user_intent": "解释这本书的主线",
                "task_hint": {"provider_group": "ai"},
                "environment_state": {"privacy_tier": "restricted", "screen_hash": "hash"},
                "attachments": [{"ref_id": "asset-1", "mime_type": "text/plain"}],
                "shell": {"shell_kind": "im_bot", "locale": "zh-CN"},
            },
        },
    }
    request.update(overrides)
    return request


def test_openharness_request_ignores_unknown_fields_and_keeps_standard_context():
    from app.infrastructure.harness.openharness.models import OpenHarnessRequest

    request = OpenHarnessRequest.model_validate({**_request(), "future_field": {"value": 1}})

    assert request.protocol_version == "1.0.0"
    assert request.request_id == "req-1"
    assert request.request.context.user_intent == "解释这本书的主线"
    assert request.request.context.attachments[0].ref_id == "asset-1"
    assert not hasattr(request, "future_field")


def test_openharness_response_contains_ordered_action_directives():
    from app.infrastructure.harness.openharness.models import (
        ActionDirective,
        OpenHarnessResponse,
        OpenHarnessResponseBody,
    )

    response = OpenHarnessResponse(
        request_id="req-1",
        correlation_id="corr-1",
        response=OpenHarnessResponseBody(
            status="success",
            action_directives=[
                ActionDirective(action_type="render_message", payload={"message": "ok"}),
                ActionDirective(
                    action_type="request_approval",
                    risk_tier="caution",
                    requires_user_approval=True,
                    payload={"message": "confirm"},
                ),
            ],
        ),
    )

    assert [item.action_type for item in response.response.action_directives] == [
        "render_message",
        "request_approval",
    ]
    assert response.response.action_directives[1].requires_user_approval is True


@pytest.mark.parametrize("version", ["2.0.0", "invalid"])
def test_parse_request_rejects_unsupported_protocol_versions(version):
    from app.infrastructure.harness.openharness.protocol import (
        OpenHarnessProtocolError,
        parse_request,
    )

    with pytest.raises(OpenHarnessProtocolError) as exc_info:
        parse_request(_request(protocol_version=version))

    assert exc_info.value.code == "protocol_version_unsupported"


def test_error_response_echoes_ids_without_leaking_details():
    from app.infrastructure.harness.openharness.protocol import error_response

    response = error_response(
        request_id="req-1",
        correlation_id="corr-1",
        code="engine_failure",
        message="The request could not be completed.",
        retryable=True,
    )

    assert response.protocol_version == "1.0.0"
    assert response.request_id == "req-1"
    assert response.correlation_id == "corr-1"
    assert response.response.status == "error"
    assert response.response.error.code == "engine_failure"
    assert "secret" not in response.model_dump_json().lower()
