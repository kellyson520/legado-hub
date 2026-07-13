from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TranslationChunk:
    id: str = ""
    job_id: str = ""
    chunk_index: int = 0
    source_text: str = ""
    translated_text: str = ""
    status: str = "queued"
    provider: str = ""
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    attempt_count: int = 0
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class TranslationJob:
    id: str = ""
    actor_id: str = ""
    source_language: str = ""
    target_language: str = ""
    status: str = "queued"
    provider: str = ""
    model: str = ""
    source_text: str = ""
    result_text: str = ""
    content_variant_id: str | None = None
    review_status: str = "candidate"
    memory_payload: dict[str, Any] = field(default_factory=dict)
    chunk_count: int = 0
    chunks: list[TranslationChunk] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
