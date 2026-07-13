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


class NovelRepository(ABC):
    """小说理解系统仓储接口"""

    # --- NovelBook ---
    @abstractmethod
    async def save_book(self, book: NovelBook) -> NovelBook: ...

    @abstractmethod
    async def get_book_by_id(self, book_id: int) -> Optional[NovelBook]: ...

    @abstractmethod
    async def get_book_by_url(self, book_url: str) -> Optional[NovelBook]: ...

    @abstractmethod
    async def list_books(self, status: Optional[NovelStatus] = None, limit: int = 20, offset: int = 0) -> List[NovelBook]: ...

    @abstractmethod
    async def count_books(self, status: Optional[NovelStatus] = None) -> int: ...

    @abstractmethod
    async def update_book_status(self, book_id: int, status: NovelStatus, progress: Optional[float] = None, error_msg: Optional[str] = None) -> bool: ...

    @abstractmethod
    async def update_book_summary(self, book_id: int, summary: str) -> bool: ...

    @abstractmethod
    async def delete_book(self, book_id: int) -> bool: ...

    # --- NovelChapter ---
    @abstractmethod
    async def save_chapter(self, chapter: NovelChapter) -> NovelChapter: ...

    @abstractmethod
    async def save_chapters_batch(self, chapters: List[NovelChapter]) -> int: ...

    @abstractmethod
    async def get_chapter_by_id(self, chapter_id: int) -> Optional[NovelChapter]: ...

    @abstractmethod
    async def get_chapters_by_book(self, book_id: int, start_num: int = 1, end_num: Optional[int] = None, limit: int = 100, offset: int = 0) -> List[NovelChapter]: ...

    @abstractmethod
    async def count_chapters(self, book_id: int) -> int: ...

    @abstractmethod
    async def update_chapter_summary(self, chapter_id: int, summary: str, key_events: List[str]) -> bool: ...

    @abstractmethod
    async def update_chapter_content(self, chapter_id: int, content: str, quality_score: Optional[float] = None) -> bool: ...

    # --- NovelEntity ---
    @abstractmethod
    async def save_entity(self, entity: NovelEntity) -> NovelEntity: ...

    @abstractmethod
    async def save_entities_batch(self, entities: List[NovelEntity]) -> int: ...

    @abstractmethod
    async def get_entity_by_id(self, entity_id: int) -> Optional[NovelEntity]: ...

    @abstractmethod
    async def get_entity_by_name(self, book_id: int, name: str) -> Optional[NovelEntity]: ...

    @abstractmethod
    async def list_entities(self, book_id: int, entity_type: Optional[EntityType] = None, limit: int = 50, offset: int = 0) -> List[NovelEntity]: ...

    @abstractmethod
    async def count_entities(self, book_id: int, entity_type: Optional[EntityType] = None) -> int: ...

    @abstractmethod
    async def get_entity_names_by_book(self, book_id: int) -> List[str]: ...

    @abstractmethod
    async def search_entities(self, book_id: int, keyword: str, entity_type: Optional[EntityType] = None, limit: int = 20) -> List[NovelEntity]: ...

    # --- NovelRelationship ---
    @abstractmethod
    async def save_relationship(self, rel: NovelRelationship) -> NovelRelationship: ...

    @abstractmethod
    async def save_relationships_batch(self, rels: List[NovelRelationship]) -> int: ...

    @abstractmethod
    async def get_relationships_by_book(self, book_id: int, limit: int = 50) -> List[NovelRelationship]: ...

    @abstractmethod
    async def get_relationships_by_entity(self, book_id: int, entity_name: str, limit: int = 50) -> List[NovelRelationship]: ...

    # --- NovelEvent ---
    @abstractmethod
    async def save_event(self, event: NovelEvent) -> NovelEvent: ...

    @abstractmethod
    async def save_events_batch(self, events: List[NovelEvent]) -> int: ...

    @abstractmethod
    async def get_events(self, book_id: int, chapter_num: Optional[int] = None, event_type: Optional[EventType] = None, min_importance: int = 1, limit: int = 50) -> List[NovelEvent]: ...

    # --- NovelStateChange ---
    @abstractmethod
    async def save_state_change(self, sc: NovelStateChange) -> NovelStateChange: ...

    @abstractmethod
    async def save_state_changes_batch(self, scs: List[NovelStateChange]) -> int: ...

    @abstractmethod
    async def get_state_changes(self, book_id: int, entity_name: Optional[str] = None, field_name: Optional[StateField] = None, limit: int = 50) -> List[NovelStateChange]: ...
