from types import SimpleNamespace

import pytest


class FakeProviderPlatform:
    def __init__(self):
        self.calls = []

    async def invoke_chat(self, provider_group, model, payload, quota_scope):
        self.calls.append({
            "provider_group": provider_group,
            "model": model,
            "payload": payload,
            "quota_scope": quota_scope,
        })
        return {
            "provider_name": "fake-provider",
            "model": model or "fake-model",
            "attempt_count": 1,
            "output": {
                "text": "主线是成长与选择。",
                "message": {"role": "assistant", "content": "主线是成长与选择。"},
                "tool_calls": [],
            },
            "usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
        }


class FakeAgentRuntime:
    def __init__(self):
        self.create_calls = []
        self.record_calls = []

    def create_run(self, **kwargs):
        self.create_calls.append(kwargs)
        return SimpleNamespace(id="run-1")

    def record_request(self, **kwargs):
        self.record_calls.append(kwargs)


def _request():
    return {
        "protocol_version": "1.0.0",
        "request_id": "req-1",
        "correlation_id": "corr-1",
        "capabilities": {"openharness.ui.rich_cards": True},
        "request": {
            "auth": {"tenant_id": "body-must-not-control-scope"},
            "context": {
                "session_id": "session-1",
                "conversation_id": "conversation-1",
                "user_intent": "请概括主线",
                "task_hint": {"provider_group": "ai", "model": "test-model"},
            },
        },
    }


@pytest.mark.asyncio
async def test_engine_maps_normalized_provider_result_to_openharness_response():
    from app.infrastructure.harness.openharness.engine import OpenHarnessEngineService
    from app.infrastructure.harness.openharness.protocol import parse_request

    service = OpenHarnessEngineService(provider_platform=FakeProviderPlatform())

    response = await service.execute(parse_request(_request()), tenant_id="user:7")

    assert response.response.status == "success"
    assert response.request_id == "req-1"
    assert response.correlation_id == "corr-1"
    assert response.response.action_directives[0].action_type == "render_message"
    assert response.response.action_directives[0].payload == {
        "message": "主线是成长与选择。",
        "format": "text",
    }
    assert response.supported_capabilities["openharness.ui.approval"] is True


@pytest.mark.asyncio
async def test_engine_does_not_trust_body_tenant_id():
    from app.infrastructure.harness.openharness.engine import OpenHarnessEngineService
    from app.infrastructure.harness.openharness.protocol import parse_request

    platform = FakeProviderPlatform()
    runtime = FakeAgentRuntime()
    service = OpenHarnessEngineService(provider_platform=platform, agent_runtime=runtime)

    await service.execute(parse_request(_request()), tenant_id="user:7")

    assert platform.calls[0]["quota_scope"] == ("user", "7")
    assert platform.calls[0]["payload"]["messages"][-1]["content"] == "请概括主线"
    assert runtime.create_calls[0]["tenant_id"] == "user:7"
    assert runtime.record_calls[0]["tenant_id"] == "user:7"
    assert runtime.record_calls[0]["owner_scope"] == "user:7"
    assert "body-must-not-control-scope" not in str(runtime.create_calls[0])
