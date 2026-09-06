"""
NovelIngestionService - 小说摄入应用层服务

编排领域服务完成小说目录摄入流程：
1. 创建/获取 NovelBook
2. 章节标题解析 + 标准化映射
3. 批量保存章节
4. 更新书籍状态
"""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import List
from urllib.parse import urlsplit
from uuid import uuid4

from app.domain.repositories.novel_repo import NovelRepository
from app.domain.services.chapter_mapper import ChapterCanonicalMapper
from app.domain.entities.novel import IngestSource, NovelBook, NovelChapter, NovelStatus
from app.domain.entities.novel_runtime import NovelAnalysisTask, NovelIngestion, NovelReadingProgress
from app.application.services.novel_ingestion.parsers import (
    NovelDocumentParser,
    ParsedChapter,
    ParsedNovelDocument,
)
from app.application.services.novel_ingestion.quality import NovelImportPreview, build_import_preview
@dataclass(frozen=True)
class ImportResult:
    book_id: int
    duplicate: bool
    status: str
    task_id: str
    error_code: str | None = None


class NovelIngestionService:
    """小说摄入服务"""

    def __init__(
        self,
        repo: NovelRepository,
        source_reader=None,
        storage_dir: str | os.PathLike[str] | None = None,
        url_policy=None,
        runtime_repo=None,
        canonical_repo=None,
    ):
        self._repo = repo
        self._source_reader = source_reader
        self._storage_dir = Path(storage_dir or os.getenv("NOVEL_STORAGE_DIR", "data/novels"))
        self._url_policy = url_policy
        self._runtime_repo = runtime_repo
        self._canonical_repo = canonical_repo

    async def prepare_upload(
        self,
        filename: str,
        media_type: str,
        data: bytes,
        *,
        title: str = "",
        author: str = "",
        split_mode: str = "heading",
        fixed_size: int = 2000,
        min_chapter_chars: int = 20,
    ) -> tuple[ParsedNovelDocument, NovelImportPreview]:
        document = NovelDocumentParser().parse(filename, media_type, data, split_mode=split_mode, fixed_size=fixed_size)
        if title or author:
            document = ParsedNovelDocument(
                title=title or document.title,
                author=author or document.author,
                normalized_text=document.normalized_text,
                chapters=document.chapters,
                content_hash=document.content_hash,
                media_type=document.media_type,
            )
        return document, build_import_preview(document, min_chapter_chars=min_chapter_chars)

    async def preview_upload(
        self,
        owner_scope: str,
        filename: str,
        media_type: str,
        data: bytes,
        *,
        title: str = "",
        author: str = "",
        split_mode: str = "heading",
        fixed_size: int = 2000,
        min_chapter_chars: int = 20,
    ) -> NovelImportPreview:
        del owner_scope
        _, preview = await self.prepare_upload(
            filename,
            media_type,
            data,
            title=title,
            author=author,
            split_mode=split_mode,
            fixed_size=fixed_size,
            min_chapter_chars=min_chapter_chars,
        )
        return preview

    async def import_document(
        self,
        owner_scope: str,
        document: ParsedNovelDocument,
        *,
        filename: str,
        media_type: str,
        data: bytes,
        title: str = "",
        author: str = "",
    ) -> ImportResult:
        content_hash = document.content_hash
        return await self._save_document(
            owner_scope,
            f"upload:{content_hash}",
            document,
            title=title or document.title,
            author=author or document.author,
            source_name="用户上传",
            source_type=IngestSource.UPLOAD,
            original=(filename, media_type, data),
        )

    async def ingest_catalog(
        self,
        book_url: str,
        book_name: str,
        raw_titles: List[str],
        author: str = "",
        source_name: str = "",
        owner_scope: str = "legacy",
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
        book = await self._repo.get_book_by_url(owner_scope, book_url)
        if book is None:
            book = NovelBook(
                owner_scope=owner_scope,
                book_url=book_url,
                book_name=book_name,
                author=author,
                source_name=source_name,
            )
            book = await self._repo.save_book(owner_scope, book)

        # 2. 检查是否已存在章节（幂等性）
        existing_chapters = await self._repo.get_chapters_by_book(owner_scope, book.id)
        if len(existing_chapters) == len(raw_titles):
            # 已存在相同数量章节，视为重复摄入，直接返回
            book.status = NovelStatus.SUMMARIZING
            return book

        # 3. 更新状态为摄入中
        book.status = NovelStatus.INGESTING
        await self._repo.update_book_status(owner_scope, book.id, NovelStatus.INGESTING)

        # 4. 章节标准化映射
        chapters = ChapterCanonicalMapper.map_batch(raw_titles, book_id=book.id)

        # 5. 批量保存章节（只保存新章节，跳过已存在的）
        existing_canonicals = {ch.canonical_full for ch in existing_chapters}
        new_chapters = [ch for ch in chapters if ch.canonical_full not in existing_canonicals]
        if new_chapters:
            await self._repo.save_chapters_batch(owner_scope, new_chapters)

        # 6. 更新书籍统计
        total = len(existing_chapters) + len(new_chapters)
        book.total_chapters = total
        book.status = NovelStatus.READY
        await self._repo.update_book_status(
            owner_scope,
            book.id,
            NovelStatus.READY,
            progress=1.0,
        )

        return book

    async def import_upload(
        self,
        owner_scope: str,
        filename: str,
        media_type: str,
        data: bytes,
        *,
        title: str = "",
        author: str = "",
    ) -> ImportResult:
        document, _ = await self.prepare_upload(filename, media_type, data, title=title, author=author)
        return await self.import_document(
            owner_scope,
            document,
            filename=filename,
            media_type=media_type,
            data=data,
            title=title,
            author=author,
        )

    async def import_source(
        self,
        owner_scope: str,
        source_id: int,
        book_url: str,
        book_name: str,
        author: str = "",
    ) -> ImportResult:
        if self._source_reader is None:
            raise ValueError("configured source reader is unavailable")
        toc = await self._source_reader.get_book_toc(source_id, book_url, book_name=book_name, author_hint=author)
        raw_chapters = toc.get("chapters", []) if isinstance(toc, dict) else toc
        chapters: list[ParsedChapter] = []
        for index, item in enumerate(raw_chapters or [], start=1):
            title = str(item.get("title") or f"第{index}章")
            chapter_url = str(item.get("url") or item.get("chapterUrl") or "")
            content_result = await self._source_reader.get_chapter_content(
                source_id,
                chapter_url,
                book_name=book_name,
                author_hint=author,
                chapter_title=title,
                chapter_index=item.get("index", index),
            )
            content = content_result.get("content", "") if isinstance(content_result, dict) else str(content_result or "")
            chapters.append(ParsedChapter(index, title, str(content).strip(), _hash_text(str(content).strip())))
        if not chapters:
            raise ValueError("configured source returned no chapters")
        normalized = "\n\n".join(chapter.text for chapter in chapters if chapter.text)
        document = ParsedNovelDocument(
            title=book_name,
            author=author,
            normalized_text=normalized,
            chapters=chapters,
            content_hash=_hash_text(normalized or book_url),
            media_type="text/plain",
        )
        return await self._save_document(
            owner_scope,
            book_url,
            document,
            title=book_name,
            author=author,
            source_name=f"书源:{source_id}",
            source_type=IngestSource.BOOK_SOURCE,
        )

    async def import_url(
        self,
        owner_scope: str,
        url: str,
        title: str = "",
        author: str = "",
    ) -> ImportResult:
        if self._url_policy is None:
            raise RuntimeError("novel URL policy is not configured")
        fetched = await self._url_policy.fetch(url)
        filename = Path(urlsplit(fetched.url).path).name or "novel.html"
        document = NovelDocumentParser().parse(filename, fetched.media_type, fetched.content)
        return await self._save_document(
            owner_scope,
            fetched.url,
            document,
            title=title or document.title,
            author=author or document.author,
            source_name=urlsplit(fetched.url).hostname or "网络链接",
            source_type=IngestSource.UPLOAD,
            original=(filename, fetched.media_type, fetched.content),
        )

    async def save_progress(
        self,
        owner_scope: str,
        book_id: int,
        chapter_id: int,
        offset_chars: int,
        percent: float,
        preferences: dict | None = None,
    ) -> dict:
        preferences = preferences or {}
        progress = NovelReadingProgress(
            owner_scope=owner_scope,
            book_id=book_id,
            chapter_id=chapter_id,
            offset_chars=max(0, int(offset_chars)),
            percent=max(0.0, min(1.0, float(percent))),
            theme=str(preferences.get("theme", "paper")),
            background=str(preferences.get("background", "")),
            font_size=max(10, min(48, int(preferences.get("font_size", preferences.get("fontSize", 18))))),
            line_height=max(1.2, min(3.0, float(preferences.get("line_height", preferences.get("lineHeight", 1.9))))),
            content_width=str(preferences.get("content_width", preferences.get("contentWidth", "comfortable"))),
        )
        saved = await self._repo.save_reading_progress(progress)
        return self._serialize_progress(saved)

    async def get_progress(self, owner_scope: str, book_id: int) -> dict | None:
        progress = await self._repo.get_reading_progress(owner_scope, book_id)
        return self._serialize_progress(progress) if progress else None

    async def _save_document(
        self,
        owner_scope: str,
        book_url: str,
        document: ParsedNovelDocument,
        *,
        title: str,
        author: str,
        source_name: str,
        source_type: IngestSource,
        original: tuple[str, str, bytes] | None = None,
    ) -> ImportResult:
        existing = await self._repo.get_book_by_url(owner_scope, book_url)
        if existing is not None:
            existing_chapters = await self._repo.get_chapters_by_book(
                owner_scope, existing.id, limit=100_000
            )
            if len(existing_chapters) >= len(document.chapters):
                await self._mirror_to_canonical(document, source_name=source_name)
                await self._ensure_initial_progress(owner_scope, existing.id)
                return ImportResult(existing.id, True, "ready", "")
            existing_keys = {chapter.canonical_full for chapter in existing_chapters}
            mapped = ChapterCanonicalMapper.map_batch(
                [parsed.title for parsed in document.chapters], book_id=existing.id
            )
            missing = []
            for parsed, chapter in zip(document.chapters, mapped):
                if chapter.canonical_full in existing_keys:
                    continue
                chapter.raw_text = parsed.text
                chapter.word_count = len(parsed.text)
                chapter.raw_text_hash = parsed.content_hash
                missing.append(chapter)
                existing_keys.add(chapter.canonical_full)
            if missing:
                await self._repo.save_chapters_batch(owner_scope, missing)
            await self._repo.update_book_status(owner_scope, existing.id, NovelStatus.READY, progress=1.0)
            await self._mirror_to_canonical(document, source_name=source_name)
            await self._ensure_initial_progress(owner_scope, existing.id)
            task_id = await self._queue_analysis(owner_scope, existing, document.normalized_text)
            return ImportResult(existing.id, True, "queued", task_id)

        book = await self._repo.save_book(
            owner_scope,
            NovelBook(
                owner_scope=owner_scope,
                book_url=book_url,
                book_name=title,
                author=author,
                source_name=source_name,
                source_type=source_type,
                total_chapters=len(document.chapters),
                total_words=len(document.normalized_text),
                status=NovelStatus.READY,
            ),
        )
        chapters: list[NovelChapter] = []
        mapped_chapters = ChapterCanonicalMapper.map_batch(
            [parsed.title for parsed in document.chapters], book_id=book.id
        )
        for parsed, chapter in zip(document.chapters, mapped_chapters):
            chapter.raw_text = parsed.text
            chapter.word_count = len(parsed.text)
            chapter.raw_text_hash = parsed.content_hash
            chapters.append(chapter)
        if chapters:
            await self._repo.save_chapters_batch(owner_scope, chapters)
            await self._repo.save_reading_progress(
                NovelReadingProgress(owner_scope=owner_scope, book_id=book.id, chapter_id=chapters[0].id)
            )
        await self._repo.update_book_status(owner_scope, book.id, NovelStatus.READY, progress=1.0)
        await self._mirror_to_canonical(document, source_name=source_name)
        if original is not None:
            self._store_original(owner_scope, document.content_hash, original)
        task_id = await self._queue_analysis(owner_scope, book, document.normalized_text)
        return ImportResult(book.id, False, "queued", task_id)

    async def _ensure_initial_progress(self, owner_scope: str, book_id: int) -> None:
        if await self._repo.get_reading_progress(owner_scope, book_id):
            return
        chapters = await self._repo.get_chapters_by_book(owner_scope, book_id)
        if chapters:
            await self._repo.save_reading_progress(
                NovelReadingProgress(owner_scope=owner_scope, book_id=book_id, chapter_id=chapters[0].id)
            )

    async def _mirror_to_canonical(self, document: ParsedNovelDocument, *, source_name: str) -> None:
        if self._canonical_repo is None:
            return
        work = self._canonical_repo.create_canonical_work(title=document.title, author="")
        existing = self._canonical_repo.list_canonical_chapters(work.id)
        if len(existing) >= len(document.chapters):
            return
        source_work = self._canonical_repo.create_source_work(
            canonical_work_id=work.id,
            source_id="upload",
            title=source_name or document.title,
            author="",
        )
        for index, parsed in enumerate(document.chapters[len(existing):], start=len(existing)):
            canonical_chapter = self._canonical_repo.add_canonical_chapter(
                canonical_work_id=work.id,
                chapter_index=index,
                title=parsed.title,
            )
            source_chapter = self._canonical_repo.add_source_chapter(
                source_work_id=source_work.id,
                chapter_index=index,
                title=parsed.title,
                chapter_url=f"upload:{document.content_hash}#chapter-{index}",
                canonical_chapter_id=canonical_chapter.id,
            )
            self._canonical_repo.add_content_variant(
                canonical_chapter_id=canonical_chapter.id,
                source_chapter_id=source_chapter.id,
                source_id="upload",
                content=parsed.text,
                health_status="healthy",
                quality_score=1.0,
                coverage_score=1.0,
                freshness_score=1.0,
                latency_ms=0,
                is_verified=True,
            )

    async def _queue_analysis(self, owner_scope: str, book: NovelBook, text: str) -> str:
        task_id = uuid4().hex
        if self._runtime_repo is None:
            return task_id
        ingestion = NovelIngestion(
            id=uuid4().hex,
            owner_scope=owner_scope,
            book_id=book.id,
            title=book.book_name,
            source_text=text,
            status="queued",
            pipeline="analysis",
        )
        self._runtime_repo.save_ingestion(ingestion)
        self._runtime_repo.save_task(
            NovelAnalysisTask(
                id=task_id,
                owner_scope=owner_scope,
                novel_id=ingestion.id,
                book_id=book.id,
                actor_id=owner_scope,
                status="queued",
                pipeline="analysis",
            )
        )
        return task_id

    def _store_original(self, owner_scope: str, content_hash: str, original: tuple[str, str, bytes]) -> Path:
        filename, media_type, data = original
        extension = NovelDocumentParser.safe_extension(filename, media_type)
        scope_hash = hashlib.sha256(owner_scope.encode("utf-8")).hexdigest()[:32]
        target_dir = self._storage_dir / scope_hash
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{content_hash}{extension}"
        if not target.exists():
            target.write_bytes(data)
            target.with_suffix(target.suffix + ".json").write_text(
                json.dumps(
                    {"filename": Path(filename).name, "media_type": media_type, "content_hash": content_hash},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        return target

    @staticmethod
    def _serialize_progress(progress: NovelReadingProgress) -> dict:
        return {
            "owner_scope": progress.owner_scope,
            "book_id": progress.book_id,
            "chapter_id": progress.chapter_id,
            "offset_chars": progress.offset_chars,
            "percent": progress.percent,
            "theme": progress.theme,
            "background": progress.background,
            "font_size": progress.font_size,
            "line_height": progress.line_height,
            "content_width": progress.content_width,
            "updated_at": progress.updated_at.isoformat() if hasattr(progress.updated_at, "isoformat") else progress.updated_at,
        }


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
