import json

import httpx
import pytest


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://api.anthropic.com", "https://api.anthropic.com/v1/messages"),
        ("https://api.anthropic.com/v1", "https://api.anthropic.com/v1/messages"),
        (
            "https://api.anthropic.com/v1/messages",
            "https://api.anthropic.com/v1/messages",
        ),
    ],
)
def test_anthropic_normalizes_messages_endpoint_once(base_url, expected):
    from app.infrastructure.providers.anthropic import _normalize_endpoint_url

    assert _normalize_endpoint_url(base_url) == expected


@pytest.mark.asyncio
async def test_anthropic_converts_openai_tools_and_normalizes_message_blocks():
    captured: dict = {}
    response_body = {
        "id": "msg_1",
        "model": "claude-3-7-sonnet",
        "content": [
            {"type": "text", "text": "已找到结果。"},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "source_search",
                "input": {"keyword": "剑来"},
            },
        ],
        "usage": {"input_tokens": 9, "output_tokens": 7},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.read())
        return httpx.Response(200, json=response_body)

    from app.infrastructure.providers.anthropic import AnthropicProvider

    provider = AnthropicProvider(
        "claude",
        "https://api.anthropic.com",
        "anthropic-secret",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.invoke_chat(
        "claude-3-7-sonnet",
        {
            "messages": [
                {"role": "system", "content": "你是书源助手。"},
                {"role": "user", "content": "搜索剑来"},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "source.search",
                        "description": "Search sources",
                        "parameters": {
                            "type": "object",
                            "properties": {"keyword": {"type": "string"}},
                        },
                    },
                },
            ],
            "tool_choice": "required",
            "max_tokens": 64,
            "temperature": 0.2,
            "unexpected": "must-not-be-forwarded",
        },
    )

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "anthropic-secret"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["body"]["system"] == "你是书源助手。"
    assert captured["body"]["messages"] == [{"role": "user", "content": "搜索剑来"}]
    assert captured["body"]["tools"] == [
        {
            "name": "source_search",
            "description": "Search sources",
            "input_schema": {
                "type": "object",
                "properties": {"keyword": {"type": "string"}},
            },
        }
    ]
    assert captured["body"]["tool_choice"] == {"type": "any"}
    assert captured["body"]["max_tokens"] == 64
    assert captured["body"]["temperature"] == 0.2
    assert "unexpected" not in captured["body"]
    assert result["provider_name"] == "claude"
    assert result["model"] == "claude-3-7-sonnet"
    assert result["output"]["text"] == "已找到结果。"
    assert result["output"]["tool_calls"] == [
        {
            "id": "toolu_1",
            "type": "function",
            "function": {
                "name": "source.search",
                "arguments": '{"keyword":"剑来"}',
            },
        }
    ]
    assert result["output"]["message"]["tool_calls"] == result["output"]["tool_calls"]
    assert result["output"]["raw"] == response_body
    assert result["usage"] == {
        "input_tokens": 9,
        "output_tokens": 7,
        "total_tokens": 16,
    }
    assert "anthropic-secret" not in str(result)
    await provider.aclose()


@pytest.mark.asyncio
async def test_anthropic_converts_tool_result_messages_and_lists_models():
    requests: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={"data": [{"id": "claude-3"}, {"id": "claude-2"}, {"id": "claude-3"}]},
            )
        body = json.loads(request.read())
        requests.append((str(request.url), body))
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    from app.infrastructure.providers.anthropic import AnthropicProvider

    provider = AnthropicProvider(
        "claude",
        "https://api.anthropic.com/v1/messages",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    await provider.invoke_chat(
        "claude-3",
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "source.search", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": '{"items": []}'},
            ]
        },
    )

    assert requests[0][0] == "https://api.anthropic.com/v1/messages"
    assert requests[0][1]["messages"] == [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "call-1", "name": "source_search", "input": {}}],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call-1",
                    "content": '{"items": []}',
                }
            ],
        },
    ]
    assert await provider.list_models() == ["claude-2", "claude-3"]
    await provider.aclose()


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        (
            "https://generativelanguage.googleapis.com",
            "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        ),
        (
            "https://generativelanguage.googleapis.com/v1beta",
            "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        ),
        (
            "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        ),
    ],
)
def test_gemini_normalizes_generate_content_endpoint_once(base_url, expected):
    from app.infrastructure.providers.gemini import _normalize_endpoint_url

    assert _normalize_endpoint_url(base_url) == expected


@pytest.mark.asyncio
async def test_gemini_converts_messages_tools_and_normalizes_function_calls():
    captured: dict = {}
    response_body = {
        "modelVersion": "gemini-2.5-pro",
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {"text": "我来搜索。"},
                        {
                            "functionCall": {
                                "name": "source_search",
                                "args": {"keyword": "剑来"},
                            }
                        },
                    ],
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 12,
            "candidatesTokenCount": 8,
            "totalTokenCount": 20,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.read())
        return httpx.Response(200, json=response_body)

    from app.infrastructure.providers.gemini import GeminiProvider

    provider = GeminiProvider(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta",
        "gemini-secret",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.invoke_chat(
        "gemini-2.5-pro",
        {
            "messages": [
                {"role": "system", "content": "你是书源助手。"},
                {"role": "user", "content": "搜索剑来"},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "source.search",
                        "description": "Search sources",
                        "parameters": {
                            "type": "object",
                            "properties": {"keyword": {"type": "string"}},
                        },
                    },
                }
            ],
            "tool_choice": "required",
            "max_tokens": 96,
            "temperature": 0.1,
            "top_p": 0.8,
            "unexpected": "must-not-be-forwarded",
        },
    )

    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-pro:generateContent?key=gemini-secret"
    )
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["body"]["systemInstruction"] == {
        "parts": [{"text": "你是书源助手。"}]
    }
    assert captured["body"]["contents"] == [
        {"role": "user", "parts": [{"text": "搜索剑来"}]}
    ]
    assert captured["body"]["tools"] == [
        {
            "function_declarations": [
                {
                    "name": "source_search",
                    "description": "Search sources",
                    "parameters": {
                        "type": "object",
                        "properties": {"keyword": {"type": "string"}},
                    },
                }
            ]
        }
    ]
    assert captured["body"]["toolConfig"] == {
        "function_calling_config": {"mode": "ANY"}
    }
    assert captured["body"]["generationConfig"] == {
        "maxOutputTokens": 96,
        "temperature": 0.1,
        "topP": 0.8,
    }
    assert "unexpected" not in captured["body"]
    assert result["provider_name"] == "gemini"
    assert result["model"] == "gemini-2.5-pro"
    assert result["output"]["text"] == "我来搜索。"
    assert result["output"]["tool_calls"] == [
        {
            "id": "call-1",
            "type": "function",
            "function": {
                "name": "source.search",
                "arguments": '{"keyword":"剑来"}',
            },
        }
    ]
    assert result["output"]["message"]["role"] == "assistant"
    assert result["usage"] == {
        "input_tokens": 12,
        "output_tokens": 8,
        "total_tokens": 20,
    }
    assert result["output"]["raw"] == response_body
    assert "gemini-secret" not in str(result)
    await provider.aclose()


@pytest.mark.asyncio
async def test_gemini_converts_tool_results_and_lists_models():
    requests: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "models/gemini-2.0-flash"},
                        {"name": "models/gemini-1.5-pro"},
                        {"name": "models/gemini-2.0-flash"},
                    ]
                },
            )
        body = json.loads(request.read())
        requests.append((str(request.url), body))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    from app.infrastructure.providers.gemini import GeminiProvider

    provider = GeminiProvider(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    await provider.invoke_chat(
        "gemini-2.0-flash",
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "source.search", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": '{"items": []}'},
            ]
        },
    )

    assert requests[0][1]["contents"] == [
        {
            "role": "model",
            "parts": [{"functionCall": {"name": "source_search", "args": {}}}],
        },
        {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "source_search",
                        "response": {"items": []},
                    }
                }
            ],
        },
    ]
    assert await provider.list_models() == ["gemini-1.5-pro", "gemini-2.0-flash"]
    await provider.aclose()
