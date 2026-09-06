from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvidenceLocation:
    chapter_id: str
    start_offset: int
    end_offset: int
    text: str


@dataclass(frozen=True)
class ChapterAnalysis:
    chapter_id: str
    chapter_index: int
    title: str
    content_sha256: str
    evidence: list[EvidenceLocation] = field(default_factory=list)


@dataclass(frozen=True)
class CharacterCandidate:
    name: str
    normalized: str
    count: int
    confidence: float
    evidence: list[EvidenceLocation] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    importance_tier: str = "minor"
    centrality: float = 0.0


@dataclass(frozen=True)
class TimeMention:
    text: str
    normalized: str
    anchor_status: str
    evidence: list[EvidenceLocation] = field(default_factory=list)


@dataclass(frozen=True)
class EventCandidate:
    trigger: str
    normalized: str
    confidence: float
    evidence: list[EvidenceLocation] = field(default_factory=list)


@dataclass(frozen=True)
class Cooccurrence:
    left: str
    right: str
    count: int
    evidence: list[EvidenceLocation] = field(default_factory=list)


@dataclass(frozen=True)
class NovelCodeAnalysisReport:
    content_sha256: str
    chapters: list[ChapterAnalysis]
    characters: list[CharacterCandidate]
    cooccurrences: list[Cooccurrence]
    time_mentions: list[TimeMention]
    events: list[EventCandidate]
    character_graph: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    cache_hit: bool = False

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)
