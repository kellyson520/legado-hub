from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class ProviderAdapter(Protocol):
    name: str

    async def invoke_chat(self, *, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def list_models(self) -> list[str]:
        ...

    async def aclose(self) -> None:
        ...


class ProviderSelection(Protocol):
    provider: ProviderAdapter
    model: str


class ProviderRegistry(Protocol):
    def resolve_group(self, group: str) -> list[ProviderSelection]:
        ...

    def snapshot(self) -> Mapping[str, list[ProviderSelection]]:
        ...
