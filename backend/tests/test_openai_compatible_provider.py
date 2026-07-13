import json

import httpx
import pytest


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://api.deepseek.com", "https://api.deepseek.com/v1/chat/completions"),
        ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1/chat/completions"),
        (
            "https://api.deepseek.com/v1/chat/completions",
            "https://api.deepseek.com/v1/chat/completions",
        ),
    ],
)
def test_normalizes_openai_compatible_base_url_once(base_url, expected):
    from app.infrastructure.providers.openai_compatible import _normalize_endpoint_url

    assert _normalize_endpoint_url(base_url) == expected


@pytest.mark.asyncio
async def test_provider_forwards_tool_fields_and_returns_tool_calls():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.read()))
        return httpx.Response(
            200,
            json={
                "model": "deepseek-chat",
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "source.inspect",
                                        "arguments": '{"url":"https://example.test"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            },
        )

    from app.infrastructure.providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        "test",
        "https://api.example.test/v1",
        "key",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.invoke_chat(
        "deepseek-chat",
        {
            "messages": [],
            "tools": [{"type": "function"}],
            "tool_choice": "auto",
            "max_tokens": 32,
            "temperature": 0.2,
        },
    )

    assert captured["tools"] == [{"type": "function"}]
    assert captured["tool_choice"] == "auto"
    assert captured["max_tokens"] == 32
    assert captured["temperature"] == 0.2
    assert result["output"]["tool_calls"][0]["function"]["name"] == "source.inspect"
    await provider.aclose()


@pytest.mark.asyncio
async def test_openai_compatible_provider_invokes_chat_completion_endpoint():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "model": "gpt-4.1-mini",
                "choices": [{"message": {"content": "hello world"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            },
        )

    from app.infrastructure.providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        name="primary-openai",
        endpoint_url="https://api.example.com/v1/chat/completions",
        api_key="secret-key",
        transport=httpx.MockTransport(handler),
    )

    result = await provider.invoke_chat(
        model="gpt-4.1-mini",
        payload={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert "Bearer secret-key" in captured["headers"].get("authorization", "")
    assert result["provider_name"] == "primary-openai"
    assert result["usage"]["input_tokens"] == 11
    await provider.aclose()


def test_build_provider_registry_registers_llm_provider_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "provider-registry.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    monkeypatch.setenv("LLM_API_URL", "https://api.example.com/v1/chat/completions")
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")

    from app.infrastructure.persistence.factory import build_provider_registry

    registry = build_provider_registry()
    providers = registry.resolve_group("ai")

    assert providers[0].name == "local-llm"
