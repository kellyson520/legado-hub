from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class PreparedEventDelivery:
    event_id: str
    event_type: str
    tenant_id: str
    body: str
    headers: dict[str, str]


@dataclass
class EventDelivery:
    event_id: str
    event_type: str
    tenant_id: str
    target_url: str
    body: str
    headers: dict[str, str] = field(default_factory=dict)
    dedupe_key: str | None = None
    status: str = 'pending'
    attempt_count: int = 0
    last_error: str | None = None
    next_attempt_at: datetime | None = None
    delivered_at: datetime | None = None
    created_at: datetime | None = None


@dataclass
class EventDeliveryAttempt:
    id: int | None
    event_id: str
    attempt_no: int
    delivered: bool
    status_code: int | None = None
    error_message: str | None = None
    created_at: datetime | None = None
