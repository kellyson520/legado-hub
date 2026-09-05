from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EvidenceSpan:
    id: str
    canonical_chapter_id: str
    content_variant_id: str
    start_offset: int
    end_offset: int
    excerpt: str
    excerpt_sha256: str
    content_sha256: str
    created_at: datetime | None = None
