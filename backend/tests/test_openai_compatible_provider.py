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
    response_body = {
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
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.read()))
        return httpx.Response(200, json=response_body)

    from app.infrastructure.providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        "test",
        "https://api.example.test/v1",
        "provider-api-key-should-not-leak",
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
            "unexpected": "must-not-be-forwarded",
        },
    )

    assert captured["tools"] == [{"type": "function"}]
    assert captured["tool_choice"] == "auto"
    assert captured["max_tokens"] == 32
    assert captured["temperature"] == 0.2
    assert "unexpected" not in captured
    provider_message = response_body["choices"][0]["message"]
    assert result["output"]["text"] == ""
    assert result["output"]["message"] == provider_message
    assert result["output"]["tool_calls"] == provider_message["tool_calls"]
    assert result["output"]["raw"] == response_body
    assert "provider-api-key-should-not-leak" not in str(result)
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


def test_build_provider_registry_keeps_env_fallback_for_groups_without_persisted_route(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "provider-route-fallback.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    monkeypatch.setenv("LLM_API_URL", "https://env.example/v1/chat/completions")
    monkeypatch.setenv("LLM_API_KEY", "env-secret")
    monkeypatch.setenv("LLM_MODEL", "env-model")

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.provider_repo_impl import SQLiteProviderRepository
    from app.infrastructure.persistence.factory import build_provider_registry

    bootstrap_sqlite()
    repo = SQLiteProviderRepository()
    persisted = repo.save_provider(
        name="persisted-ai",
        base_url="https://persisted.example/v1",
        api_key="persisted-secret",
        default_model="persisted-model",
        enabled=True,
    )
    repo.replace_routes("ai", [{"provider_account_id": persisted.id, "model": "persisted-model"}])

    registry = build_provider_registry()

    assert registry.resolve_group("ai")[0].name == "persisted-ai"
    assert registry.resolve_group("source_build")[0].name == "local-llm"
