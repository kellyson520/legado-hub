from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WorkKnowledgeProposal:
    id: str
    work_id: str
    source_chapter_id: str
    proposal_type: str
    subject: str = ''
    relation: str = ''
    object_name: str = ''
    evidence: str = ''
    payload: dict = field(default_factory=dict)
    status: str = 'candidate'
    revision_of: str | None = None
    created_by: str = ''
    reviewed_by: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    published_at: datetime | None = None
