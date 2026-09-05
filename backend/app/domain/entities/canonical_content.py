from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CanonicalWork:
    id: str
    title: str
    author: str
    normalized_title: str = ''
    normalized_author: str = ''
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class SourceWork:
    id: str
    canonical_work_id: str
    source_id: str
    title: str
    author: str
    normalized_title: str = ''
    normalized_author: str = ''
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class CanonicalChapter:
    id: str
    canonical_work_id: str
    chapter_index: int
    title: str
    normalized_title: str = ''
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class SourceChapter:
    id: str
    source_work_id: str
    chapter_index: int
    title: str
    chapter_url: str
    canonical_chapter_id: str | None = None
    normalized_title: str = ''
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class ChapterAlignment:
    id: str
    canonical_chapter_id: str
    source_chapter_id: str
    confidence: float
    evidence: dict = field(default_factory=dict)
    review_status: str = 'accepted'
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class ContentVariant:
    id: str
    canonical_chapter_id: str
    source_chapter_id: str
    source_id: str
    content: str
    health_status: str = 'unknown'
    quality_score: float = 0.0
    coverage_score: float = 0.0
    freshness_score: float = 0.0
    latency_ms: int = 0
    is_verified: bool = True
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class RouteDecision:
    id: str
    tenant_id: str
    canonical_chapter_id: str
    selected_variant_id: str | None
    fallback_count: int
    route_summary: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class ChapterMatch:
    canonical_index: int
    source_index: int
    confidence: float
    canonical_title: str
    source_title: str
    review_status: str = 'accepted'
    canonical_chapter_id: str | None = None
    source_chapter_id: str | None = None


@dataclass
class AlignmentResult:
    matches: list[ChapterMatch] = field(default_factory=list)
    review_items: list[dict] = field(default_factory=list)
