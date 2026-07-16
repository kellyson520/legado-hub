from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.entities.event_delivery import EventDelivery, EventDeliveryAttempt


class EventDeliveryRepository(ABC):
    @abstractmethod
    def get(self, event_id: str) -> EventDelivery | None:
        raise NotImplementedError

    @abstractmethod
    def get_by_dedupe_key(self, tenant_id: str, dedupe_key: str) -> EventDelivery | None:
        raise NotImplementedError

    @abstractmethod
    def list_due(self, *, now: datetime, limit: int = 20) -> list[EventDelivery]:
        raise NotImplementedError

    @abstractmethod
    def list_deliveries(self, limit: int = 50) -> list[EventDelivery]:
        raise NotImplementedError

    @abstractmethod
    def list_deliveries_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
    ) -> tuple[list[EventDelivery], int]:
        raise NotImplementedError

    @abstractmethod
    def save(self, delivery: EventDelivery) -> EventDelivery:
        raise NotImplementedError

    @abstractmethod
    def record_attempt(
        self,
        *,
        event_id: str,
        attempt: EventDeliveryAttempt,
        status: str,
        attempt_count: int,
        last_error: str | None,
        next_attempt_at: datetime | None,
        delivered_at: datetime | None,
    ) -> EventDelivery:
        raise NotImplementedError

    @abstractmethod
    def list_attempts(self, event_id: str) -> list[EventDeliveryAttempt]:
        raise NotImplementedError
