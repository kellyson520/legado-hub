from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Job:
    id: str
    kind: str
    tenant_id: str
    payload: dict = field(default_factory=dict)
    idempotency_key: str | None = None
    status: str = 'queued'
    attempt_count: int = 0
    worker_id: str | None = None
    lease_token: str | None = None
    lease_expires_at: datetime | None = None
    available_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime | None = None


@dataclass
class JobEvent:
    id: int | None
    job_id: str
    tenant_id: str
    event_type: str
    detail: dict = field(default_factory=dict)
    created_at: datetime | None = None
