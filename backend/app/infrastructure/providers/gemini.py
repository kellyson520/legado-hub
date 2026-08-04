from __future__ import annotations

import copy
import json
import re
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx


_TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")
_GENERATE_SUFFIX = "/models/{model}:generateContent"


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


def _prepare_tools(tools: object) -> tuple[object, dict[str, str], dict[str, str]]:
    if not isinstance(tools, list):
        return tools, {}, {}
    internal_to_wire, wire_to_internal = _safe_tool_maps(tools)
    declarations: list[dict[str, Any]] = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("function_declarations"), list):
            source_items = item["function_declarations"]
        else:
            source_items = [item]
        for source_item in source_items:
            if not isinstance(source_item, dict):
                continue
            function = source_item.get("function")
            source = function if isinstance(function, dict) else source_item
            name = source.get("name") if isinstance(source, dict) else None
            if not isinstance(name, str) or not name:
                continue
            description = source.get("description", "")
            if not isinstance(description, str):
                description = str(description)
            schema = source.get("parameters", source.get("input_schema"))
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            declarations.append(
                {
                    "name": internal_to_wire.get(name, _wire_tool_name(name)),
                    "description": description,
                    "parameters": copy.deepcopy(schema),
                }
            )
    return (
        [{"function_declarations": declarations}],
        internal_to_wire,
        wire_to_internal,
    )


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
    arguments = value if isinstance(value, dict) else _json_object(value)
    return json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))


def _content_to_parts(content: object) -> list[dict[str, Any]]:
    if content is None:
        return []
    if isinstance(content, str):
        return [{"text": content}] if content else []
    if isinstance(content, dict):
        if content.get("type") == "text":
            return [{"text": str(content.get("text", ""))}]
        if "text" in content and isinstance(content.get("text"), str):
            return [{"text": content["text"]}]
        return [copy.deepcopy(content)]
    if isinstance(content, list):
        parts: list[dict[str, Any]] = []
        for item in content:
            if isinstance(item, str):
                parts.append({"text": item})
                continue
            if not isinstance(item, dict):
                parts.append({"text": str(item)})
                continue
            item_type = item.get("type")
            if item_type == "text":
                parts.append({"text": str(item.get("text", ""))})
            elif item_type == "image_url":
                image_url = item.get("image_url")
                url = image_url.get("url") if isinstance(image_url, dict) else image_url
                if isinstance(url, str) and url:
                    parts.append({"fileData": {"fileUri": url}})
            else:
                parts.append(copy.deepcopy(item))
        return parts
    return [{"text": str(content)}]


def _prepare_messages(
    messages: object,
    internal_to_wire: dict[str, str],
) -> tuple[list[dict[str, Any]], object]:
    prepared: list[dict[str, Any]] = []
    system_values: list[object] = []
    tool_names_by_id: dict[str, str] = {}
    if not isinstance(messages, list):
        return prepared, None

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user")
        content = message.get("content", "")
        if role == "system":
            system_values.extend(_content_to_parts(content))
            continue
        if role in {"tool", "function"}:
            call_id = str(message.get("tool_call_id") or message.get("id") or "")
            function_name = tool_names_by_id.get(call_id, _wire_tool_name(call_id or "tool"))
            prepared.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": function_name,
                                "response": _json_object(message.get("content")),
                            }
                        }
                    ],
                }
            )
            continue
        wire_role = "model" if role == "assistant" else "user"
        parts = _content_to_parts(content)
        if role == "assistant" and isinstance(message.get("tool_calls"), list):
            for index, call in enumerate(message["tool_calls"]):
                if not isinstance(call, dict):
                    continue
                function = call.get("function")
                if not isinstance(function, dict):
                    continue
                name = function.get("name")
                if not isinstance(name, str) or not name:
                    continue
                wire_name = internal_to_wire.get(name, _wire_tool_name(name))
                call_id = str(call.get("id") or f"call-{index + 1}")
                tool_names_by_id[call_id] = wire_name
                parts.append(
                    {
                        "functionCall": {
                            "name": wire_name,
                            "args": _json_object(function.get("arguments")),
                        }
                    }
                )
        prepared.append({"role": wire_role, "parts": parts})

    if not system_values:
        return prepared, None
    return prepared, {"parts": system_values}


def _merge_system_values(explicit: object, message_system: object) -> object:
    if explicit is None:
        if message_system is None:
            return None
        return message_system
    explicit_parts = _content_to_parts(explicit)
    if message_system is None:
        return {"parts": explicit_parts}
    message_parts = message_system.get("parts", []) if isinstance(message_system, dict) else []
    return {"parts": explicit_parts + list(message_parts)}


def _prepare_tool_choice(choice: object, internal_to_wire: dict[str, str]) -> object:
    if isinstance(choice, str):
        mode = {"auto": "AUTO", "required": "ANY", "any": "ANY", "none": "NONE"}.get(choice)
        return {"function_calling_config": {"mode": mode}} if mode else choice
    if not isinstance(choice, dict):
        return choice
    if isinstance(choice.get("function_calling_config"), dict):
        prepared = copy.deepcopy(choice)
        config = prepared["function_calling_config"]
        names = config.get("allowed_function_names")
        if isinstance(names, list):
            config["allowed_function_names"] = [
                internal_to_wire.get(name, _wire_tool_name(name))
                for name in names
                if isinstance(name, str)
            ]
        return prepared
    function = choice.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return {
            "function_calling_config": {
                "mode": "ANY",
                "allowed_function_names": [
                    internal_to_wire.get(function["name"], _wire_tool_name(function["name"]))
                ],
            }
        }
    choice_type = choice.get("type")
    if choice_type in {"auto", "required", "any", "none"}:
        mode = {"auto": "AUTO", "required": "ANY", "any": "ANY", "none": "NONE"}[choice_type]
        return {"function_calling_config": {"mode": mode}}
    return copy.deepcopy(choice)


def _normalize_endpoint_url(endpoint_url: str) -> str:
    parts = urlsplit(endpoint_url.strip())
    path = parts.path.rstrip("/")
    if ":generateContent" in path and "/models/" in path:
        prefix = path[: path.index("/models/")]
        normalized_path = f"{prefix}{_GENERATE_SUFFIX}"
    elif path.endswith("/models"):
        normalized_path = f"{path}/{{model}}:generateContent"
    elif path.endswith("/v1beta") or path.endswith("/v1"):
        normalized_path = f"{path}{_GENERATE_SUFFIX}"
    else:
        normalized_path = f"{path}/v1beta{_GENERATE_SUFFIX}" if path else f"/v1beta{_GENERATE_SUFFIX}"
    return urlunsplit((parts.scheme, parts.netloc, normalized_path, parts.query, parts.fragment))


def _models_endpoint_url(endpoint_url: str) -> str:
    parts = urlsplit(_normalize_endpoint_url(endpoint_url))
    path = parts.path
    marker = "/models/{model}:generateContent"
    if marker in path:
        path = f"{path[:path.index(marker)]}/models"
    else:
        path = f"{path.rstrip('/')}/models"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _with_api_key(url: str, api_key: str) -> str:
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "key"]
    if api_key:
        query.append(("key", api_key))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _render_endpoint(endpoint_url: str, model: str, api_key: str) -> str:
    model_name = model.removeprefix("models/")
    rendered = endpoint_url.replace("{model}", quote(model_name, safe="-._~"))
    return _with_api_key(rendered, api_key)


def _as_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


class GeminiProvider:
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
        contents, message_system = _prepare_messages(payload.get("messages", []), internal_to_wire)
        request_body: dict[str, Any] = {"contents": contents}
        system_instruction = _merge_system_values(payload.get("system"), message_system)
        if system_instruction is not None:
            request_body["systemInstruction"] = system_instruction
        if isinstance(tools, list):
            request_body["tools"] = tools
        if "tool_choice" in payload:
            tool_config = _prepare_tool_choice(payload["tool_choice"], internal_to_wire)
            if isinstance(tool_config, dict):
                request_body["toolConfig"] = tool_config
        generation_config: dict[str, Any] = {}
        for source, target in (
            ("max_tokens", "maxOutputTokens"),
            ("max_output_tokens", "maxOutputTokens"),
            ("temperature", "temperature"),
            ("top_p", "topP"),
            ("stop_sequences", "stopSequences"),
        ):
            if source in payload:
                generation_config[target] = payload[source]
        if "stop" in payload and "stop_sequences" not in payload:
            generation_config["stopSequences"] = payload["stop"]
        if generation_config:
            request_body["generationConfig"] = generation_config

        response = await self._client.post(
            _render_endpoint(self._endpoint_url, model, self._api_key),
            headers={"Content-Type": "application/json"},
            json=request_body,
        )
        response.raise_for_status()
        raw = response.json()
        body = raw if isinstance(raw, dict) else {}
        candidates = body.get("candidates", [])
        candidate = (
            candidates[0]
            if isinstance(candidates, list)
            and candidates
            and isinstance(candidates[0], dict)
            else {}
        )
        content = candidate.get("content", {})
        parts = content.get("parts", []) if isinstance(content, dict) else []
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict):
                    continue
                if "text" in part:
                    text_parts.append(str(part.get("text", "")))
                function_call = part.get("functionCall")
                if not isinstance(function_call, dict):
                    continue
                name = function_call.get("name")
                if not isinstance(name, str) or not name:
                    continue
                tool_calls.append(
                    {
                        "id": str(function_call.get("id") or f"call-{len(tool_calls) + 1}"),
                        "type": "function",
                        "function": {
                            "name": wire_to_internal.get(name, name),
                            "arguments": _tool_arguments(function_call.get("args")),
                        },
                    }
                )
        text = "".join(text_parts)
        usage = body.get("usageMetadata", {})
        if not isinstance(usage, dict):
            usage = {}
        input_tokens = _as_int(usage.get("promptTokenCount"))
        output_tokens = _as_int(usage.get("candidatesTokenCount", usage.get("outputTokenCount")))
        total_tokens = _as_int(usage.get("totalTokenCount")) or input_tokens + output_tokens
        message = {"role": "assistant", "content": text, "tool_calls": tool_calls}
        return {
            "provider_name": self.name,
            "model": body.get("modelVersion", body.get("model", model)),
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
        response = await self._client.get(_with_api_key(_models_endpoint_url(self._endpoint_url), self._api_key))
        response.raise_for_status()
        raw = response.json()
        data = raw.get("models", []) if isinstance(raw, dict) else []
        model_ids: set[str] = set()
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            name = item["name"].strip()
            if name.startswith("models/"):
                name = name[len("models/") :]
            if name:
                model_ids.add(name)
        return sorted(model_ids)

    async def aclose(self) -> None:
        await self._client.aclose()


GeminiProviderAdapter = GeminiProvider
