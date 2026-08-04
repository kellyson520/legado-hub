from __future__ import annotations

import copy
import json
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


_ANTHROPIC_VERSION = "2023-06-01"
_TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


def _wire_tool_name(name: str) -> str:
    if _TOOL_NAME.fullmatch(name):
        return name
    normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", name).strip("_")
    return normalized or "tool"


def _safe_tool_maps(tools: object) -> tuple[dict[str, str], dict[str, str]]:
    internal_to_wire: dict[str, str] = {}
    wire_to_internal: dict[str, str] = {}
    used: set[str] = set()
    if not isinstance(tools, list):
        return internal_to_wire, wire_to_internal

    for item in tools:
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        source = function if isinstance(function, dict) else item
        name = source.get("name") if isinstance(source, dict) else None
        if not isinstance(name, str) or not name:
            continue
        wire_name = _wire_tool_name(name)
        if wire_name in used and wire_to_internal.get(wire_name) != name:
            suffix = 2
            candidate = f"{wire_name}_{suffix}"
            while candidate in used:
                suffix += 1
                candidate = f"{wire_name}_{suffix}"
            wire_name = candidate
        used.add(wire_name)
        internal_to_wire[name] = wire_name
        wire_to_internal[wire_name] = name
    return internal_to_wire, wire_to_internal


def _tool_schema(item: dict[str, Any]) -> tuple[str | None, str, Any]:
    function = item.get("function")
    source = function if isinstance(function, dict) else item
    name = source.get("name") if isinstance(source, dict) else None
    if not isinstance(name, str) or not name:
        return None, "", {"type": "object", "properties": {}}
    description = source.get("description", "")
    if not isinstance(description, str):
        description = str(description)
    schema = source.get("parameters", source.get("input_schema"))
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}
    return name, description, copy.deepcopy(schema)


def _prepare_tools(tools: object) -> tuple[object, dict[str, str], dict[str, str]]:
    if not isinstance(tools, list):
        return tools, {}, {}
    internal_to_wire, wire_to_internal = _safe_tool_maps(tools)
    prepared: list[dict[str, Any]] = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        name, description, schema = _tool_schema(item)
        if name is None:
            continue
        prepared.append(
            {
                "name": internal_to_wire[name],
                "description": description,
                "input_schema": schema,
            }
        )
    return prepared, internal_to_wire, wire_to_internal


def _content_to_anthropic(content: object) -> object:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks: list[object] = []
        for item in content:
            if isinstance(item, str):
                blocks.append({"type": "text", "text": item})
            elif isinstance(item, dict) and item.get("type") == "text":
                blocks.append({"type": "text", "text": str(item.get("text", ""))})
            elif isinstance(item, dict):
                blocks.append(copy.deepcopy(item))
        return blocks
    if isinstance(content, dict):
        return copy.deepcopy(content)
    return str(content)


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {"raw": value}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    if value is None:
        return {}
    return {"value": value}


def _tool_arguments(value: object) -> str:
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except (TypeError, ValueError):
            return json.dumps({"raw": value}, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


def _prepare_messages(
    messages: object,
    internal_to_wire: dict[str, str],
) -> tuple[list[dict[str, Any]], object]:
    prepared: list[dict[str, Any]] = []
    system_values: list[object] = []
    if not isinstance(messages, list):
        return prepared, None

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user")
        content = message.get("content", "")
        if role == "system":
            system_values.append(_content_to_anthropic(content))
            continue
        if role in {"tool", "function"}:
            tool_call_id = str(message.get("tool_call_id") or message.get("id") or "")
            prepared.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": _content_to_anthropic(content),
                        }
                    ],
                }
            )
            continue
        if role == "assistant" and isinstance(message.get("tool_calls"), list):
            blocks: list[object] = []
            converted_content = _content_to_anthropic(content)
            if isinstance(converted_content, list):
                blocks.extend(converted_content)
            elif converted_content:
                blocks.append({"type": "text", "text": str(converted_content)})
            for index, call in enumerate(message["tool_calls"]):
                if not isinstance(call, dict):
                    continue
                function = call.get("function")
                if not isinstance(function, dict):
                    continue
                name = function.get("name")
                if not isinstance(name, str) or not name:
                    continue
                call_id = str(call.get("id") or f"call-{index + 1}")
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call_id,
                        "name": internal_to_wire.get(name, _wire_tool_name(name)),
                        "input": _json_object(function.get("arguments")),
                    }
                )
            prepared.append({"role": "assistant", "content": blocks or ""})
            continue
        prepared.append(
            {
                "role": "assistant" if role == "assistant" else "user",
                "content": _content_to_anthropic(content),
            }
        )

    if not system_values:
        return prepared, None
    if len(system_values) == 1:
        return prepared, system_values[0]
    if all(isinstance(value, str) for value in system_values):
        return prepared, "\n\n".join(str(value) for value in system_values)
    blocks: list[object] = []
    for value in system_values:
        if isinstance(value, list):
            blocks.extend(value)
        else:
            blocks.append({"type": "text", "text": str(value)})
    return prepared, blocks


def _merge_system_values(explicit: object, message_system: object) -> object:
    if explicit is None:
        return message_system
    if message_system is None:
        return explicit
    if isinstance(explicit, str) and isinstance(message_system, str):
        return f"{explicit}\n\n{message_system}"
    values: list[object] = []
    for value in (explicit, message_system):
        if isinstance(value, list):
            values.extend(value)
        elif isinstance(value, str):
            values.append({"type": "text", "text": value})
        else:
            values.append(copy.deepcopy(value))
    return values


def _prepare_tool_choice(choice: object, internal_to_wire: dict[str, str]) -> object:
    if isinstance(choice, str):
        return {
            "auto": {"type": "auto"},
            "required": {"type": "any"},
            "any": {"type": "any"},
            "none": None,
        }.get(choice, choice)
    if not isinstance(choice, dict):
        return choice
    if isinstance(choice.get("function"), dict):
        name = choice["function"].get("name")
        if isinstance(name, str):
            return {"type": "tool", "name": internal_to_wire.get(name, _wire_tool_name(name))}
    choice_type = choice.get("type")
    if choice_type in {"auto", "any", "none"}:
        return {"type": choice_type} if choice_type != "none" else None
    if choice_type in {"required", "function"}:
        name = choice.get("name")
        if isinstance(name, str):
            return {"type": "tool", "name": internal_to_wire.get(name, _wire_tool_name(name))}
        return {"type": "any"}
    if choice_type == "tool" and isinstance(choice.get("name"), str):
        name = choice["name"]
        return {"type": "tool", "name": internal_to_wire.get(name, _wire_tool_name(name))}
    return copy.deepcopy(choice)


def _normalize_endpoint_url(endpoint_url: str) -> str:
    parts = urlsplit(endpoint_url.strip())
    path = parts.path.rstrip("/")
    if path.endswith("/v1/messages"):
        normalized_path = path
    elif path.endswith("/messages"):
        normalized_path = path
    elif path.endswith("/v1"):
        normalized_path = f"{path}/messages"
    else:
        normalized_path = f"{path}/v1/messages" if path else "/v1/messages"
    return urlunsplit((parts.scheme, parts.netloc, normalized_path, parts.query, parts.fragment))


def _models_endpoint_url(endpoint_url: str) -> str:
    normalized = _normalize_endpoint_url(endpoint_url)
    parts = urlsplit(normalized)
    path = parts.path.rstrip("/")
    if path.endswith("/messages"):
        path = f"{path[:-len('/messages')]}/models"
    else:
        path = f"{path}/models"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _as_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


class AnthropicProvider:
    def __init__(
        self,
        name: str,
        endpoint_url: str,
        api_key: str,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.name = name
        self._endpoint_url = _normalize_endpoint_url(endpoint_url)
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def invoke_chat(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        tools, internal_to_wire, wire_to_internal = _prepare_tools(payload.get("tools"))
        messages, message_system = _prepare_messages(payload.get("messages", []), internal_to_wire)
        request_body: dict[str, Any] = {
            "model": model,
            "max_tokens": payload.get("max_tokens", 1024),
            "messages": messages,
        }
        system = _merge_system_values(payload.get("system"), message_system)
        if system is not None:
            request_body["system"] = system
        if isinstance(tools, list):
            request_body["tools"] = tools
        if "tool_choice" in payload:
            tool_choice = _prepare_tool_choice(payload["tool_choice"], internal_to_wire)
            if tool_choice is not None:
                request_body["tool_choice"] = tool_choice
        for source, target in (
            ("temperature", "temperature"),
            ("top_p", "top_p"),
            ("stop_sequences", "stop_sequences"),
        ):
            if source in payload:
                request_body[target] = payload[source]
        if "stop" in payload and "stop_sequences" not in payload:
            request_body["stop_sequences"] = payload["stop"]

        response = await self._client.post(
            self._endpoint_url,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
            json=request_body,
        )
        response.raise_for_status()
        raw = response.json()
        body = raw if isinstance(raw, dict) else {}
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        content = body.get("content", [])
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for index, block in enumerate(content):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text_parts.append(str(block.get("text", "")))
                elif block.get("type") == "tool_use":
                    name = block.get("name")
                    if not isinstance(name, str) or not name:
                        continue
                    tool_calls.append(
                        {
                            "id": str(block.get("id") or f"call-{index + 1}"),
                            "type": "function",
                            "function": {
                                "name": wire_to_internal.get(name, name),
                                "arguments": _tool_arguments(block.get("input")),
                            },
                        }
                    )
        text = "".join(text_parts)
        usage = body.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        input_tokens = _as_int(usage.get("input_tokens"))
        output_tokens = _as_int(usage.get("output_tokens"))
        total_tokens = _as_int(usage.get("total_tokens")) or input_tokens + output_tokens
        message = {"role": "assistant", "content": text, "tool_calls": tool_calls}
        return {
            "provider_name": self.name,
            "model": body.get("model", model),
            "output": {
                "text": text,
                "message": message,
                "tool_calls": tool_calls,
                "raw": raw,
            },
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            "raw": raw,
        }

    async def list_models(self) -> list[str]:
        response = await self._client.get(
            _models_endpoint_url(self._endpoint_url),
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
            },
        )
        response.raise_for_status()
        raw = response.json()
        data = raw.get("data", []) if isinstance(raw, dict) else []
        return sorted(
            {
                str(item["id"])
                for item in data
                if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip()
            }
        )

    async def aclose(self) -> None:
        await self._client.aclose()


AnthropicProviderAdapter = AnthropicProvider
