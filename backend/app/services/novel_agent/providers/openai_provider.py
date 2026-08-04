"""
OpenAI 兼容 Provider 实现
支持 DeepSeek、OpenAI 等所有 OpenAI 兼容 API
"""
from __future__ import annotations

import json
import asyncio
from typing import AsyncIterator, List, Optional

import httpx

from . import (
    BaseProvider, register_provider, ProviderConfig,
    Message, ToolSchema, ToolCall, StreamChunk, Usage, ProviderError, ProviderHTTPError, ProviderStreamError,
)


@register_provider("openai")
class OpenAIProvider(BaseProvider):
    """OpenAI 兼容 API Provider"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            timeout=120.0,
        )
        self._api_key = config.get_api_key()

    async def stream(self, messages: List[Message], system: str = "",
                     tools: Optional[List[ToolSchema]] = None,
                     temperature: float = 0.7, max_tokens: int = 4096) -> AsyncIterator[StreamChunk]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.config.model,
            "messages": self._format_messages(messages, system),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "tool_choice": "auto",
        }

        if tools:
            payload["tools"] = self._format_tools(tools)

        accumulated_tool_calls = {}
        current_tool_idx = None

        try:
            async with self._client.stream(
                "POST", "/v1/chat/completions",
                headers=headers, json=payload
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    error = ProviderHTTPError(
                        response.status_code,
                        f"HTTP {response.status_code}: {error_text.decode('utf-8', errors='replace')}",
                    )
                    yield StreamChunk(error=str(error), exception=error)
                    return

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break

                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    choices = event.get("choices", [])
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta", {})

                    content = delta.get("content", "")
                    if content:
                        yield StreamChunk(text=content)

                    tool_calls_delta = delta.get("tool_calls", [])
                    if tool_calls_delta:
                        for tc_delta in tool_calls_delta:
                            idx = tc_delta.get("index", 0)
                            if idx not in accumulated_tool_calls:
                                accumulated_tool_calls[idx] = ToolCall(
                                    id=tc_delta.get("id", f"call_{idx}"),
                                    name=tc_delta.get("function", {}).get("name", ""),
                                    arguments="",
                                )
                            current_tool_idx = idx
                            func_delta = tc_delta.get("function", {})
                            if "name" in func_delta:
                                accumulated_tool_calls[idx].name = func_delta["name"]
                            if "arguments" in func_delta:
                                accumulated_tool_calls[idx].arguments += func_delta["arguments"]

                    finish_reason = choice.get("finish_reason")
                    if finish_reason == "tool_calls" and accumulated_tool_calls:
                        tool_calls_list = [accumulated_tool_calls[k] for k in sorted(accumulated_tool_calls.keys())]
                        yield StreamChunk(tool_calls=tool_calls_list)

                    usage = event.get("usage")
                    if usage:
                        yield StreamChunk(usage=self._parse_usage(usage))

        except Exception as e:
            error = e if isinstance(e, ProviderError) else ProviderStreamError(str(e), cause=e)
            yield StreamChunk(error=str(error), exception=error)

    async def complete(self, messages: List[Message], system: str = "",
                       tools: Optional[List[ToolSchema]] = None,
                       temperature: float = 0.7, max_tokens: int = 4096) -> tuple[str, List[ToolCall], Usage]:
        full_text = ""
        tool_calls: List[ToolCall] = []
        usage = Usage()

        async for chunk in self.stream(messages, system, tools, temperature, max_tokens):
            if chunk.error:
                if chunk.exception is not None:
                    raise chunk.exception
                raise ProviderStreamError(chunk.error)
            if chunk.text:
                full_text += chunk.text
            if chunk.tool_calls:
                tool_calls = chunk.tool_calls
            if chunk.usage:
                usage = chunk.usage

        return full_text, tool_calls, usage

    def _format_messages(self, messages: List[Message], system: str) -> list:
        result = []
        if system:
            result.append({"role": "system", "content": system})

        for msg in messages:
            item = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.role == "tool" and msg.tool_call_id:
                item["tool_call_id"] = msg.tool_call_id
            if msg.name:
                item["name"] = msg.name
            result.append(item)

        return result

    def _format_tools(self, tools: List[ToolSchema]) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _parse_usage(self, usage: dict) -> Usage:
        return Usage(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            cache_hit_tokens=usage.get("prompt_cache_hit_tokens", 0),
            cache_miss_tokens=usage.get("prompt_cache_miss_tokens", 0),
        )
