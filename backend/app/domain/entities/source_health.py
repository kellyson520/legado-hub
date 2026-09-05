from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SourceHealthSnapshot:
    source_id: int
    source_name: str
    source_url: str
    health_status: str = "unknown"
    search_status: str = "unknown"
    toc_status: str = "unknown"
    content_status: str = "unknown"
    failure_reason: str = ""
    decision_confidence: str = "low"
    route_policy: str = "probe_only"
    route_score: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_success_at: datetime | None = None
    last_probe_at: datetime | None = None
    next_probe_at: datetime | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SourceProbeRun:
    source_id: int
    source_name: str
    probe_mode: str
    keyword: str
    overall_status: str
    failure_reason: str
    id: str = field(default_factory=lambda: uuid4().hex)
    search_result: dict = field(default_factory=dict)
    toc_result: dict = field(default_factory=dict)
    content_result: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class StageProbeResult:
    stage: str
    status: str = "unknown"
    elapsed_ms: int = 0
    request_preview: str = ""
    response_kind: str = ""
    hit_count: int = 0
    sample_title: str = ""
    error_message: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class SourceProbeEvidence:
    source_id: int
    source_name: str
    source_url: str
    probe_mode: str
    keyword: str
    search: StageProbeResult
    toc: StageProbeResult
    content: StageProbeResult
    attempted_keywords: list[str] = field(default_factory=list)
    attempts: list[dict] = field(default_factory=list)


@dataclass
class SourceHealthDecision:
    source_id: int
    source_name: str
    source_url: str
    health_status: str
    search_status: str
    toc_status: str
    content_status: str
    failure_reason: str
    decision_confidence: str
    route_policy: str
    route_score: float
    metadata: dict = field(default_factory=dict)
