from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class NovelIngestion:
    id: str = ""
    title: str = ""
    source_text: str = ""
    status: str = "pending"
    provider: str = ""
    pipeline: str = "analysis"
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class NovelAnalysisTask:
    id: str = ""
    novel_id: str = ""
    actor_id: str = ""
    status: str = "queued"
    provider: str = ""
    model: str = ""
    pipeline: str = "analysis"
    result: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
