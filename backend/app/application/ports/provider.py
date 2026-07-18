from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


PROVIDER_ROUTE_GROUPS = (
    "default",
    "ai",
    "source_build",
    "translation",
    "novel",
    "novel_extract",
    "novel_verify",
    "novel_adjudicate",
    "novel_audit",
)


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


def provider_http_status(exc: BaseException) -> int | None:
    """Read an optional HTTP status without depending on an HTTP library."""

    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None
