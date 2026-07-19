import copy
import re

import httpx


_OPENAI_TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


def _wire_tool_name(name: str) -> str:
    """Convert internal dotted tool names to names accepted by OpenAI-compatible APIs."""

    if _OPENAI_TOOL_NAME.fullmatch(name):
        return name
    normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", name).strip("_")
    return normalized or "tool"


def _prepare_tools(tools: object) -> tuple[object, dict[str, str], dict[str, str]]:
    if not isinstance(tools, list):
        return tools, {}, {}
    prepared = copy.deepcopy(tools)
    internal_to_wire: dict[str, str] = {}
    wire_to_internal: dict[str, str] = {}
    used_wire_names: set[str] = set()
    for item in prepared:
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        if not isinstance(function, dict) or not isinstance(function.get("name"), str):
            continue
        internal_name = function["name"]
        wire_name = _wire_tool_name(internal_name)
        if wire_name in used_wire_names and wire_to_internal.get(wire_name) != internal_name:
            suffix = 2
            candidate = f"{wire_name}_{suffix}"
            while candidate in used_wire_names:
                suffix += 1
                candidate = f"{wire_name}_{suffix}"
            wire_name = candidate
        used_wire_names.add(wire_name)
        internal_to_wire[internal_name] = wire_name
        wire_to_internal[wire_name] = internal_name
        function["name"] = wire_name
    return prepared, internal_to_wire, wire_to_internal


def _prepare_messages(messages: object, internal_to_wire: dict[str, str]) -> object:
    if not isinstance(messages, list):
        return messages
    prepared = copy.deepcopy(messages)
    for message in prepared:
        if not isinstance(message, dict):
            continue
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                continue
            name = function["name"]
            function["name"] = internal_to_wire.get(name, _wire_tool_name(name))
    return prepared


def _prepare_tool_choice(tool_choice: object, internal_to_wire: dict[str, str]) -> object:
    if not isinstance(tool_choice, dict):
        return tool_choice
    prepared = copy.deepcopy(tool_choice)
    function = prepared.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        name = function["name"]
        function["name"] = internal_to_wire.get(name, _wire_tool_name(name))
    return prepared


def _restore_message_tool_names(message: object, wire_to_internal: dict[str, str]) -> dict:
    restored = copy.deepcopy(message) if isinstance(message, dict) else {}
    tool_calls = restored.get("tool_calls")
    if not isinstance(tool_calls, list):
        return restored
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function")
        if not isinstance(function, dict) or not isinstance(function.get("name"), str):
            continue
        function["name"] = wire_to_internal.get(function["name"], function["name"])
    return restored


def _normalize_endpoint_url(endpoint_url: str) -> str:
    normalized = endpoint_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return normalized + "/chat/completions"
    return normalized + "/v1/chat/completions"


def _models_endpoint_url(endpoint_url: str) -> str:
    normalized = _normalize_endpoint_url(endpoint_url)
    suffix = "/chat/completions"
    if normalized.endswith(suffix):
        return normalized[: -len(suffix)] + "/models"
    return normalized.rstrip("/") + "/models"


class OpenAICompatibleProvider:
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

    async def invoke_chat(self, model: str, payload: dict) -> dict:
        tools, internal_to_wire, wire_to_internal = _prepare_tools(payload.get("tools"))
        request_body = {
            "model": model,
            "messages": _prepare_messages(payload.get("messages", []), internal_to_wire),
        }
        if tools is not None:
            request_body["tools"] = tools
        if "tool_choice" in payload:
            request_body["tool_choice"] = _prepare_tool_choice(payload["tool_choice"], internal_to_wire)
        for field in ("temperature", "max_tokens"):
            if field in payload:
                request_body[field] = payload[field]
        response = await self._client.post(
            self._endpoint_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
        if self._should_retry_tool_choice(response, request_body):
            fallback_body = copy.deepcopy(request_body)
            fallback_body["tool_choice"] = "auto"
            response = await self._client.post(
                self._endpoint_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=fallback_body,
            )
        response.raise_for_status()
        body = response.json()
        choices = body.get("choices", [])
        message = _restore_message_tool_names(
            choices[0].get("message", {}) if choices else {},
            wire_to_internal,
        )
        content = message.get("content") or ""
        usage = body.get("usage", {})
        return {
            "provider_name": self.name,
            "model": body.get("model", model),
            "output": {
                "text": content,
                "message": message,
                "tool_calls": message.get("tool_calls") or [],
                "raw": body,
            },
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "raw": body,
        }

    @staticmethod
    def _should_retry_tool_choice(response: httpx.Response, request_body: dict) -> bool:
        if response.status_code != 400 or request_body.get("tool_choice") != "required":
            return False
        try:
            payload = response.json()
        except ValueError:
            return False
        error = payload.get("error") if isinstance(payload, dict) else None
        message = error.get("message", "") if isinstance(error, dict) else ""
        normalized = str(message).lower()
        return "thinking mode" in normalized and "tool_choice" in normalized

    async def list_models(self) -> list[str]:
        response = await self._client.get(
            _models_endpoint_url(self._endpoint_url),
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        response.raise_for_status()
        body = response.json()
        data = body.get("data", []) if isinstance(body, dict) else []
        return sorted(
            {
                str(item["id"])
                for item in data
                if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip()
            }
        )

    async def aclose(self) -> None:
        await self._client.aclose()
