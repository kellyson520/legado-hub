from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SystemSetting:
    key: str = ""
    value: str = ""
    updated_at: datetime = field(default_factory=utcnow)
