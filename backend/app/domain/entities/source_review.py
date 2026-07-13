from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SourceReviewItem:
    id: str = ""
    review_type: str = ""
    source_version_id: str | None = None
    source_url: str = ""
    summary: str = ""
    payload: dict = field(default_factory=dict)
    status: str = "candidate"
    created_by: str = ""
    reviewed_by: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    resolved_at: datetime | None = None
