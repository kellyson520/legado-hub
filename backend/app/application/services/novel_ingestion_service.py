"""
NovelIngestionService - 小说摄入应用层服务

编排领域服务完成小说目录摄入流程：
1. 创建/获取 NovelBook
2. 章节标题解析 + 标准化映射
3. 批量保存章节
4. 更新书籍状态
"""

from typing import List

from app.domain.repositories.novel_repo import NovelRepository
from app.domain.services.chapter_mapper import ChapterCanonicalMapper
from app.domain.entities.novel import NovelBook, NovelStatus


class NovelIngestionService:
    """小说摄入服务"""

    def __init__(self, repo: NovelRepository):
        self._repo = repo

    async def ingest_catalog(
        self,
        book_url: str,
        book_name: str,
        raw_titles: List[str],
        author: str = "",
        source_name: str = "",
    ) -> NovelBook:
        """
        摄入小说目录

        Args:
            book_url: 书籍URL
            book_name: 书名
            raw_titles: 原始章节标题列表
            author: 作者
            source_name: 来源站点名称

        Returns:
            更新后的 NovelBook
        """
        # 1. 查找或创建书籍
        book = await self._repo.get_book_by_url(book_url)
        if book is None:
            book = NovelBook(
                book_url=book_url,
                book_name=book_name,
                author=author,
                source_name=source_name,
            )
            book = await self._repo.save_book(book)

        # 2. 检查是否已存在章节（幂等性）
        existing_chapters = await self._repo.get_chapters_by_book(book.id)
        if len(existing_chapters) == len(raw_titles):
            # 已存在相同数量章节，视为重复摄入，直接返回
            book.status = NovelStatus.SUMMARIZING
            return book

        # 3. 更新状态为摄入中
        book.status = NovelStatus.INGESTING
        await self._repo.update_book_status(book.id, NovelStatus.INGESTING)

        # 4. 章节标准化映射
        chapters = ChapterCanonicalMapper.map_batch(raw_titles, book_id=book.id)

        # 5. 批量保存章节（只保存新章节，跳过已存在的）
        existing_canonicals = {ch.canonical_full for ch in existing_chapters}
        new_chapters = [ch for ch in chapters if ch.canonical_full not in existing_canonicals]
        if new_chapters:
            await self._repo.save_chapters_batch(new_chapters)

        # 6. 更新书籍统计
        total = len(existing_chapters) + len(new_chapters)
        book.total_chapters = total
        book.status = NovelStatus.SUMMARIZING
        await self._repo.update_book_status(
            book.id,
            NovelStatus.SUMMARIZING,
            progress=0.3,
        )

        return book
