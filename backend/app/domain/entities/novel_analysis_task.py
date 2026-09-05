from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class NovelAnalysisTask:
    id: str
    work_id: str
    tenant_id: str
    goal: str
    status: str = "queued"
    policy: dict = field(default_factory=dict)
    checkpoint: dict = field(default_factory=dict)
    tool_call_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class AdjudicationOutcome:
    verdict: str
    claim_status: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskProcessingResult:
    """Bounded result of one evidence-first analysis task execution."""

    claim_ids: tuple[str, ...] = ()
    outcomes: tuple[AdjudicationOutcome, ...] = ()
    token_count: int = 0
    reasons: tuple[str, ...] = ()
