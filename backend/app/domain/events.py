"""Domain events shared by application use cases and event infrastructure.

The event bus is an infrastructure concern. Event payloads are domain
contracts and therefore live in the domain layer so domain code never needs to
import logging, asyncio, or a transport implementation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class DomainEvent:
    event_id: str = field(default_factory=lambda: f"evt_{datetime.utcnow().timestamp()}")
    timestamp: datetime = field(default_factory=datetime.utcnow)
    trace_id: Optional[str] = None

    def event_type(self) -> str:
        return self.__class__.__name__


@dataclass
class SourceFetchedEvent(DomainEvent):
    subscription_id: int = 0
    subscription_name: str = ""
    book_count: int = 0
    rss_count: int = 0
    status: str = "success"
    message: str = ""


@dataclass
class SourceStatusChangedEvent(DomainEvent):
    source_url: str = ""
    source_name: str = ""
    source_type: str = ""
    old_status: str = ""
    new_status: str = ""
    error_msg: Optional[str] = None


@dataclass
class SourceCreatedEvent(DomainEvent):
    source_url: str = ""
    source_name: str = ""
    source_type: str = ""
    created_by: Optional[int] = None


@dataclass
class SourceUpdatedEvent(DomainEvent):
    source_url: str = ""
    source_name: str = ""
    source_type: str = ""
    changed_fields: List[str] = field(default_factory=list)


@dataclass
class SourceDeletedEvent(DomainEvent):
    source_url: str = ""
    source_name: str = ""
    source_type: str = ""


@dataclass
class FilterRuleTriggeredEvent(DomainEvent):
    rule_id: int = 0
    rule_name: str = ""
    source_url: str = ""
    source_name: str = ""
    match_field: str = ""


@dataclass
class QuotaUsageEvent(DomainEvent):
    api_key_id: int = 0
    metric: str = ""
    amount: int = 0
    total_used: int = 0
    limit: int = 0


@dataclass
class QuotaExceededEvent(DomainEvent):
    api_key_id: int = 0
    metric: str = ""
    used: int = 0
    limit: int = 0


@dataclass
class AIAnalysisCompletedEvent(DomainEvent):
    analysis_type: str = ""
    book_url: str = ""
    book_name: str = ""
    result_id: int = 0
    chars_consumed: int = 0
    status: str = "success"


@dataclass
class ChapterComplementRequestedEvent(DomainEvent):
    job_id: str = ""
    book_name: str = ""
    chapter_title: str = ""
    chapter_num: int = 0
    source_urls: List[str] = field(default_factory=list)
    priority: str = "normal"


@dataclass
class ChapterFetchedFromSourceEvent(DomainEvent):
    job_id: str = ""
    source_url: str = ""
    source_name: str = ""
    chapter_title: str = ""
    chapter_num: int = 0
    content: str = ""
    word_count: int = 0
    success: bool = True
    error: Optional[str] = None
    response_time_ms: int = 0


@dataclass
class ChapterComplementCompletedEvent(DomainEvent):
    job_id: str = ""
    book_name: str = ""
    chapter_title: str = ""
    chapter_num: int = 0
    total_sources: int = 0
    successful_sources: int = 0
    final_content: str = ""
    final_word_count: int = 0
    quality_score: float = 0.0
    source_contributions: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "success"
    merged_from: List[str] = field(default_factory=list)


@dataclass
class SourceComplementProgressEvent(DomainEvent):
    job_id: str = ""
    total_sources: int = 0
    completed_sources: int = 0
    failed_sources: int = 0
    progress: float = 0.0
    status: str = "running"


@dataclass
class AuditEvent(DomainEvent):
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    user_id: Optional[int] = None
    api_key_id: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: Optional[str] = None


@dataclass
class SystemNoticeEvent(DomainEvent):
    level: str = "info"
    title: str = ""
    content: str = ""
    target: str = "all"


@dataclass
class TranslationStartedEvent(DomainEvent):
    job_id: str = ""
    book_url: str = ""
    book_name: str = ""
    chapter_title: str = ""
    total_chunks: int = 0


@dataclass
class TranslationCompletedEvent(DomainEvent):
    job_id: str = ""
    book_url: str = ""
    book_name: str = ""
    chapter_title: str = ""
    status: str = "completed"
    progress: float = 0.0


@dataclass
class TranslationProgressEvent(DomainEvent):
    job_id: str = ""
    completed_chunks: int = 0
    total_chunks: int = 0
    progress: float = 0.0


@dataclass
class DictionaryUpdatedEvent(DomainEvent):
    book_url: str = ""
    book_name: str = ""
    new_entries: Dict[str, Any] = field(default_factory=dict)
    total_entries: int = 0


__all__ = [
    "DomainEvent",
    "SourceFetchedEvent",
    "SourceStatusChangedEvent",
    "SourceCreatedEvent",
    "SourceUpdatedEvent",
    "SourceDeletedEvent",
    "FilterRuleTriggeredEvent",
    "QuotaUsageEvent",
    "QuotaExceededEvent",
    "AIAnalysisCompletedEvent",
    "ChapterComplementRequestedEvent",
    "ChapterFetchedFromSourceEvent",
    "ChapterComplementCompletedEvent",
    "SourceComplementProgressEvent",
    "AuditEvent",
    "SystemNoticeEvent",
    "TranslationStartedEvent",
    "TranslationCompletedEvent",
    "TranslationProgressEvent",
    "DictionaryUpdatedEvent",
]
