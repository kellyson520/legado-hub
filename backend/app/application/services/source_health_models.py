from __future__ import annotations

from dataclasses import dataclass, field


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
