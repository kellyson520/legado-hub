from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.entities.event_delivery import EventDelivery


@dataclass(frozen=True)
class OutboundHttpResponse:
    """Transport-neutral response data exposed to application services."""

    status_code: int
    text: str = ""


class WebhookSender(Protocol):
    def __call__(self, delivery: EventDelivery) -> OutboundHttpResponse:
        """Deliver one already-signed event payload."""


class AsyncHttpClient(Protocol):
    async def get(self, url: str, **kwargs):
        ...

    async def post(self, url: str, **kwargs):
        ...

    async def aclose(self) -> None:
        ...
