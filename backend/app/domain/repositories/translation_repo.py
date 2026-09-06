"""
翻译模块仓储接口（抽象）

领域层只定义接口，不依赖任何存储实现。
基础设施层提供具体实现（SQLite、PostgreSQL 等）。
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from ..entities.translation import TranslationJob, TranslationChunk, TranslationDictionary


class TranslationRepository(ABC):
    """翻译模块仓储接口"""

    # ==================== TranslationJob ====================

    @abstractmethod
    async def get_job(self, job_id: str) -> Optional[TranslationJob]:
        """根据业务 job_id 获取翻译任务"""
        pass

    @abstractmethod
    async def get_job_by_id(self, id: int) -> Optional[TranslationJob]:
        """根据数据库 ID 获取翻译任务"""
        pass

    @abstractmethod
    async def list_jobs(
        self,
        book_url: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> tuple[List[TranslationJob], int]:
        """列出翻译任务，返回 (列表, 总数)"""
        pass

    @abstractmethod
    async def save_job(self, job: TranslationJob) -> TranslationJob:
        """保存或更新翻译任务"""
        pass

    @abstractmethod
    async def delete_job(self, job_id: str) -> bool:
        """删除翻译任务"""
        pass

    # ==================== TranslationChunk ====================

    @abstractmethod
    async def get_chunk(self, job_id: str, chunk_index: int) -> Optional[TranslationChunk]:
        """获取指定任务的指定块"""
        pass

    @abstractmethod
    async def list_chunks(self, job_id: str) -> List[TranslationChunk]:
        """列出任务的所有块"""
        pass

    @abstractmethod
    async def save_chunk(self, job_id: str, chunk: TranslationChunk) -> TranslationChunk:
        """保存或更新翻译块"""
        pass

    @abstractmethod
    async def save_chunks(self, job_id: str, chunks: List[TranslationChunk]) -> int:
        """批量保存翻译块"""
        pass

    @abstractmethod
    async def delete_chunks(self, job_id: str) -> bool:
        """删除任务的所有块"""
        pass

    # ==================== TranslationDictionary ====================

    @abstractmethod
    async def get_dictionary(self, book_url: str) -> Optional[TranslationDictionary]:
        """获取书籍的翻译词典"""
        pass

    @abstractmethod
    async def save_dictionary(self, dictionary: TranslationDictionary) -> TranslationDictionary:
        """保存或更新翻译词典"""
        pass

    @abstractmethod
    async def delete_dictionary(self, book_url: str) -> bool:
        """删除翻译词典"""
        pass
