from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SourceDefinition:
    id: int = 0
    source_type: str = ""
    source_key: str = ""
    source_name: str = ""
    source_group: str = "default"
    enabled: bool = True
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class SourceVersion:
    id: str = ""
    source_definition_id: int = 0
    source_type: str = ""
    source_id: str = ""
    status: str = "draft"
    payload: dict = field(default_factory=dict)
    created_by: str = ""
    created_at: datetime = field(default_factory=utcnow)
    published_at: datetime | None = None


@dataclass
class SourceTestRun:
    id: str = ""
    source_version_id: str = ""
    trigger: str = ""
    score: int = 0
    grade: str = ""
    step_results: dict = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class SourceDeployment:
    id: str = ""
    source_version_id: str = ""
    action: str = ""
    status: str = ""
    quality_gate: dict = field(default_factory=dict)
    actor_id: str = ""
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class SourceHealthEvent:
    id: int = 0
    source_version_id: str = ""
    event_type: str = ""
    detail: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
