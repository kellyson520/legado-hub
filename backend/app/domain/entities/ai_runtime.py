from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AITask:
    id: str = ""
    kind: str = ""
    actor_id: str = ""
    provider: str = ""
    model: str = ""
    status: str = "queued"
    prompt_payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
