from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


EpistemicState = Literal["explicit", "inferred", "speculative"]
ClaimStatus = Literal["candidate", "published", "superseded", "withdrawn"]


@dataclass(frozen=True)
class KnowledgeEntity:
    id: str
    work_id: str
    name: str
    entity_type: str = "character"
    created_at: datetime | None = None


@dataclass(frozen=True)
class KnowledgeClaim:
    id: str
    work_id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str | None
    scalar_value: Any | None
    epistemic: EpistemicState
    status: ClaimStatus = "candidate"
    evidence_ids: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    published_at: datetime | None = None


@dataclass(frozen=True)
class KnowledgeConflict:
    id: str
    work_id: str
    incumbent_claim_id: str
    conflicting_claim_id: str
    status: str = "open"
    created_at: datetime | None = None


@dataclass(frozen=True)
class Publishability:
    allowed: bool
    reasons: tuple[str, ...] = ()
