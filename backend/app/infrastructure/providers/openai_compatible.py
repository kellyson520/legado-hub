import httpx


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


def _embeddings_endpoint_url(endpoint_url: str) -> str:
    normalized = endpoint_url.rstrip("/")
    if normalized.endswith("/embeddings"):
        return normalized
    if normalized.endswith("/chat/completions"):
        return normalized[: -len("/chat/completions")] + "/embeddings"
    if normalized.endswith("/v1"):
        return normalized + "/embeddings"
    return normalized + "/v1/embeddings"


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
        request_body = {
            "model": model,
            "messages": payload.get("messages", []),
        }
        for field in ("tools", "tool_choice", "temperature", "max_tokens"):
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
        response.raise_for_status()
        body = response.json()
        choices = body.get("choices", [])
        message = choices[0].get("message", {}) if choices else {}
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

    async def invoke_embedding(self, model: str, payload: dict) -> dict:
        request_body = {"model": model, "input": payload.get("input", [])}
        for field in ("encoding_format", "dimensions", "user"):
            if field in payload:
                request_body[field] = payload[field]
        response = await self._client.post(
            _embeddings_endpoint_url(self._endpoint_url),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage", {}) if isinstance(body, dict) else {}
        return {
            "provider_name": self.name,
            "model": body.get("model", model) if isinstance(body, dict) else model,
            "data": body.get("data", []) if isinstance(body, dict) else [],
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": 0,
                "total_tokens": usage.get("total_tokens", usage.get("prompt_tokens", 0)),
            },
            "raw": body,
        }

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
