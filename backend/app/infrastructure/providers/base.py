from typing import Any, Protocol


class ProviderAdapter(Protocol):
    name: str

    async def invoke_chat(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def invoke_embedding(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
