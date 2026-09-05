from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.domain.entities.source_runtime import SourceVersion


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SourceRuleVersion:
    id: str
    canonical_url: str
    status: str = 'candidate'
    payload: dict = field(default_factory=dict)
    created_by: str = ''
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def from_source_version(cls, version: SourceVersion, *, canonical_url: str) -> 'SourceRuleVersion':
        return cls(
            id=version.id,
            canonical_url=canonical_url,
            status=version.status,
            payload=version.payload,
            created_by=version.created_by,
            created_at=version.created_at,
        )
