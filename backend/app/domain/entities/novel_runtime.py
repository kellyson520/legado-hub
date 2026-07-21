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
    owner_scope: str = "legacy"
    book_id: int | None = None


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
    owner_scope: str = "legacy"
    book_id: int | None = None
    chapter_id: int | None = None


@dataclass
class NovelIndexState:
    owner_scope: str
    book_id: int
    chapter_id: int | None = None
    content_hash: str = ""
    knowledge_version: str = ""
    extraction_status: str = "pending"
    bm25_status: str = "pending"
    vector_status: str = "disabled"
    embedding_model: str = ""
    embedding_dimension: int = 0
    last_success_at: datetime | None = None
    failure_reason: str = ""
    updated_at: datetime = field(default_factory=utcnow)


@dataclass
class NovelReadingProgress:
    owner_scope: str
    book_id: int
    chapter_id: int
    offset_chars: int = 0
    percent: float = 0.0
    theme: str = "paper"
    background: str = ""
    font_size: int = 18
    line_height: float = 1.9
    content_width: str = "comfortable"
    updated_at: datetime = field(default_factory=utcnow)


@dataclass
class NovelModelPreference:
    owner_scope: str
    scope_type: str
    scope_id: str
    task_type: str
    model_ref: str
    provider_group: str = "novel"
    updated_at: datetime = field(default_factory=utcnow)
