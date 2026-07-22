"""
NovelUnderstanding 自主进化引擎 - 仓储接口（抽象）

定义所有 Novel 相关实体的持久化操作，遵循 DDD 仓储模式。
实现类在 infrastructure 层提供（如 SqliteNovelRepository）。
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from ..entities.novel import (
    NovelBook, NovelChapter, NovelEntity, NovelRelationship,
    NovelEvent, NovelStateChange, NovelStatus, EntityType, EventType, StateField
)
from ..entities.novel_runtime import (
    NovelAdjudicationCandidate,
    NovelIndexState,
    NovelReadingProgress,
)


class NovelRepository(ABC):
    """小说理解系统仓储接口"""

    # --- NovelBook ---
    @abstractmethod
    async def save_book(self, owner_scope: str, book: NovelBook) -> NovelBook: ...

    @abstractmethod
    async def get_book_by_id(self, owner_scope: str, book_id: int) -> Optional[NovelBook]: ...

    @abstractmethod
    async def get_book_by_url(self, owner_scope: str, book_url: str) -> Optional[NovelBook]: ...

    async def claim_legacy_scope(self, owner_scope: str) -> dict: ...

    @abstractmethod
    async def list_books(self, owner_scope: str | None, status: Optional[NovelStatus] = None, limit: int = 20, offset: int = 0) -> List[NovelBook]: ...

    @abstractmethod
    async def count_books(self, owner_scope: str, status: Optional[NovelStatus] = None) -> int: ...

    @abstractmethod
    async def update_book_status(self, owner_scope: str, book_id: int, status: NovelStatus, progress: Optional[float] = None, error_msg: Optional[str] = None) -> bool: ...

    @abstractmethod
    async def update_book_summary(self, owner_scope: str, book_id: int, summary: str) -> bool: ...

    @abstractmethod
    async def delete_book(self, owner_scope: str, book_id: int) -> bool: ...

    # --- NovelChapter ---
    @abstractmethod
    async def save_chapter(self, owner_scope: str, chapter: NovelChapter) -> NovelChapter: ...

    @abstractmethod
    async def save_chapters_batch(self, owner_scope: str, chapters: List[NovelChapter]) -> int: ...

    @abstractmethod
    async def get_chapter_by_id(self, owner_scope: str, chapter_id: int) -> Optional[NovelChapter]: ...

    @abstractmethod
    async def get_chapters_by_book(self, owner_scope: str, book_id: int, start_num: int = 0, end_num: Optional[int] = None, limit: int = 100, offset: int = 0) -> List[NovelChapter]: ...

    @abstractmethod
    async def count_chapters(self, owner_scope: str, book_id: int) -> int: ...

    @abstractmethod
    async def update_chapter_summary(self, owner_scope: str, chapter_id: int, summary: str, key_events: List[str]) -> bool: ...

    @abstractmethod
    async def update_chapter_content(self, owner_scope: str, chapter_id: int, content: str, quality_score: Optional[float] = None) -> bool: ...

    # --- NovelEntity ---
    @abstractmethod
    async def save_entity(self, owner_scope: str, entity: NovelEntity) -> NovelEntity: ...

    @abstractmethod
    async def save_entities_batch(self, owner_scope: str, entities: List[NovelEntity]) -> int: ...

    @abstractmethod
    async def get_entity_by_id(self, owner_scope: str, entity_id: int) -> Optional[NovelEntity]: ...

    @abstractmethod
    async def get_entity_by_name(self, owner_scope: str, book_id: int, name: str) -> Optional[NovelEntity]: ...

    @abstractmethod
    async def list_entities(self, owner_scope: str, book_id: int, entity_type: Optional[EntityType] = None, limit: int = 50, offset: int = 0) -> List[NovelEntity]: ...

    @abstractmethod
    async def count_entities(self, owner_scope: str, book_id: int, entity_type: Optional[EntityType] = None) -> int: ...

    @abstractmethod
    async def get_entity_names_by_book(self, owner_scope: str, book_id: int) -> List[str]: ...

    @abstractmethod
    async def search_entities(self, owner_scope: str, book_id: int, keyword: str, entity_type: Optional[EntityType] = None, limit: int = 20) -> List[NovelEntity]: ...

    # --- NovelRelationship ---
    @abstractmethod
    async def save_relationship(self, owner_scope: str, rel: NovelRelationship) -> NovelRelationship: ...

    @abstractmethod
    async def save_relationships_batch(self, owner_scope: str, rels: List[NovelRelationship]) -> int: ...

    @abstractmethod
    async def get_relationships_by_book(self, owner_scope: str, book_id: int, limit: int = 50) -> List[NovelRelationship]: ...

    @abstractmethod
    async def get_relationships_by_entity(self, owner_scope: str, book_id: int, entity_name: str, limit: int = 50) -> List[NovelRelationship]: ...

    # --- NovelEvent ---
    @abstractmethod
    async def save_event(self, owner_scope: str, event: NovelEvent) -> NovelEvent: ...

    @abstractmethod
    async def save_events_batch(self, owner_scope: str, events: List[NovelEvent]) -> int: ...

    @abstractmethod
    async def get_events(self, owner_scope: str, book_id: int, chapter_num: Optional[int] = None, event_type: Optional[EventType] = None, min_importance: int = 1, limit: int = 50) -> List[NovelEvent]: ...

    # --- NovelStateChange ---
    @abstractmethod
    async def save_state_change(self, owner_scope: str, sc: NovelStateChange) -> NovelStateChange: ...

    @abstractmethod
    async def save_state_changes_batch(self, owner_scope: str, scs: List[NovelStateChange]) -> int: ...

    @abstractmethod
    async def get_state_changes(self, owner_scope: str, book_id: int, entity_name: Optional[str] = None, field_name: Optional[StateField] = None, limit: int = 50) -> List[NovelStateChange]: ...

    @abstractmethod
    async def save_index_state(self, state: NovelIndexState) -> NovelIndexState: ...

    @abstractmethod
    async def get_index_state(self, owner_scope: str, book_id: int, chapter_id: int | None = None) -> Optional[NovelIndexState]: ...

    @abstractmethod
    async def list_index_states(self, owner_scope: str, book_id: int) -> List[NovelIndexState]: ...

    @abstractmethod
    async def replace_book_knowledge(self, owner_scope: str, book_id: int, snapshots: List[dict]) -> dict[str, int]: ...

    @abstractmethod
    async def update_book_statistics(self, owner_scope: str, book_id: int, counts: dict[str, int]) -> bool: ...

    @abstractmethod
    async def upsert_adjudication_candidate(self, candidate: NovelAdjudicationCandidate) -> NovelAdjudicationCandidate: ...

    @abstractmethod
    async def list_adjudication_candidates(self, owner_scope: str, book_id: int, status: str | None = None, limit: int = 100) -> List[NovelAdjudicationCandidate]: ...

    @abstractmethod
    async def update_adjudication_candidate(self, owner_scope: str, candidate_id: int, *, status: str | None = None, decision: dict | None = None, attempts: int | None = None) -> bool: ...

    @abstractmethod
    async def save_evolution_feedback(self, owner_scope: str, feedback) -> object: ...

    @abstractmethod
    async def list_evolution_feedback(self, owner_scope: str, book_id: int, applied: bool | None = None, limit: int = 100, offset: int = 0) -> list: ...

    @abstractmethod
    async def list_evolution_rules(self, owner_scope: str, book_id: int, rule_type: str | None = None, active: bool | None = None, limit: int = 100) -> list: ...

    @abstractmethod
    async def list_active_evolution_rules(self, owner_scope: str, book_id: int, rule_types: list[str] | None = None, limit: int = 100) -> list: ...

    @abstractmethod
    async def apply_evolution_update(self, owner_scope: str, book_id: int, feedback, rule) -> object: ...

    @abstractmethod
    async def save_reading_progress(self, progress: NovelReadingProgress) -> NovelReadingProgress: ...

    @abstractmethod
    async def get_reading_progress(self, owner_scope: str, book_id: int) -> Optional[NovelReadingProgress]: ...
