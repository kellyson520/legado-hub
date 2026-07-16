from dataclasses import dataclass, field
from hashlib import sha256
from urllib.parse import urlparse


@dataclass(frozen=True)
class IngestedChapter:
    canonical_work_id: str
    canonical_chapter_id: str
    source_chapter_id: str
    content_variant_id: str
    evidence_span_ids: list[str]
    title: str
    content: str
    changed_prior_variant_ids: list[str] = field(default_factory=list)


class WorkIngestionService:
    def __init__(
        self,
        *,
        reader,
        source_repo,
        source_runtime_repo,
        source_health_repo,
        canonical_repo,
        evidence_service,
        evidence_max_chars: int = 800,
    ):
        self._reader = reader
        self._source_repo = source_repo
        self._source_runtime_repo = source_runtime_repo
        self._source_health_repo = source_health_repo
        self._canonical_repo = canonical_repo
        self._evidence_service = evidence_service
        self._evidence_max_chars = evidence_max_chars

    async def fetch_and_ingest_chapter(
        self,
        *,
        source_id: int,
        book_url: str,
        chapter_index: int,
        book_name: str,
        author_hint: str | None,
    ) -> IngestedChapter:
        source = await self._require_healthy_published_source(source_id)
        self._assert_source_url(source, book_url)
        if not isinstance(chapter_index, int) or chapter_index < 0:
            raise ValueError("chapter_index must be a non-negative integer")

        toc = await self._reader.get_book_toc(
            source_id,
            book_url,
            book_name,
            author_hint,
        )
        if toc.get("resolved_source_id") != source_id:
            raise ValueError("source fallback is not permitted for evidence ingestion")
        chapters = toc.get("chapters") if isinstance(toc, dict) else None
        if not isinstance(chapters, list) or chapter_index >= len(chapters):
            raise ValueError("chapter_index is outside the returned table of contents")
        chapter = chapters[chapter_index]
        if not isinstance(chapter, dict) or not isinstance(chapter.get("url"), str):
            raise ValueError("table of contents chapter is invalid")

        content_response = await self._reader.get_chapter_content(
            source_id,
            chapter["url"],
            book_name,
            author_hint,
            str(chapter.get("title") or ""),
            chapter_index,
        )
        if content_response.get("resolved_source_id") != source_id:
            raise ValueError("source fallback is not permitted for evidence ingestion")
        content = content_response.get("content") if isinstance(content_response, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("chapter content is unavailable")

        title = str(chapter.get("title") or content_response.get("title") or f"Chapter {chapter_index + 1}")
        work = self._canonical_repo.create_canonical_work(
            title=book_name.strip(),
            author=(author_hint or "").strip(),
        )
        canonical_chapter = self._canonical_chapter(work.id, chapter_index, title)
        changed_prior_variant_ids = [
            variant.id
            for variant in self._canonical_repo.list_content_variants(canonical_chapter.id)
            if variant.source_id == str(source_id)
            and self._content_fingerprint(variant.content) != self._content_fingerprint(content)
        ]
        source_work = self._canonical_repo.create_source_work(
            canonical_work_id=work.id,
            source_id=str(source_id),
            title=book_name,
            author=author_hint or "",
        )
        source_chapter = self._canonical_repo.add_source_chapter(
            source_work_id=source_work.id,
            chapter_index=chapter_index,
            title=title,
            chapter_url=chapter["url"],
            canonical_chapter_id=canonical_chapter.id,
        )
        variant = self._canonical_repo.add_content_variant(
            canonical_chapter_id=canonical_chapter.id,
            source_chapter_id=source_chapter.id,
            source_id=str(source_id),
            content=content,
            health_status="healthy",
            quality_score=1.0,
            coverage_score=1.0,
            freshness_score=1.0,
            latency_ms=0,
            is_verified=True,
        )
        spans = self._evidence_service.create_spans(
            content_variant_id=variant.id,
            canonical_chapter_id=canonical_chapter.id,
            content=content,
            max_chars=self._evidence_max_chars,
        )
        return IngestedChapter(
            canonical_work_id=work.id,
            canonical_chapter_id=canonical_chapter.id,
            source_chapter_id=source_chapter.id,
            content_variant_id=variant.id,
            evidence_span_ids=[span.id for span in spans],
            title=title,
            content=content,
            changed_prior_variant_ids=changed_prior_variant_ids,
        )

    async def search_sources(
        self,
        *,
        keyword: str,
        source_ids: list[int] | None = None,
        author_hint: str | None = None,
    ) -> dict:
        sources = await self._source_repo.list_book_sources_full(enabled_only=True, ids=source_ids)
        eligible_ids = []
        for source in sources:
            try:
                await self._require_healthy_published_source(int(source["id"]))
            except (LookupError, PermissionError, ValueError):
                continue
            eligible_ids.append(int(source["id"]))
        if not eligible_ids:
            raise PermissionError("no healthy published sources are available")
        return await self._reader.search_books(
            keyword,
            source_ids=eligible_ids,
            limit_per_source=3,
            author_hint=author_hint,
        )

    async def get_table_of_contents(
        self,
        *,
        source_id: int,
        book_url: str,
        book_name: str,
        author_hint: str | None,
    ) -> dict:
        source = await self._require_healthy_published_source(source_id)
        self._assert_source_url(source, book_url)
        toc = await self._reader.get_book_toc(source_id, book_url, book_name, author_hint)
        if toc.get("resolved_source_id") != source_id:
            raise ValueError("source fallback is not permitted for evidence ingestion")
        chapters = toc.get("chapters") if isinstance(toc, dict) else None
        if not isinstance(chapters, list):
            raise ValueError("table of contents is unavailable")
        return {
            "source_id": source_id,
            "book_url": book_url,
            "chapters": [
                {"index": index, "title": str(chapter.get("title") or f"Chapter {index + 1}")}
                for index, chapter in enumerate(chapters)
                if isinstance(chapter, dict) and isinstance(chapter.get("url"), str)
            ],
        }

    async def resolve_book(
        self,
        *,
        source_id: int,
        book_url: str,
        book_name: str,
        author_hint: str | None,
    ) -> dict:
        toc = await self.get_table_of_contents(
            source_id=source_id,
            book_url=book_url,
            book_name=book_name,
            author_hint=author_hint,
        )
        return {
            "source_id": source_id,
            "book_url": book_url,
            "chapter_count": len(toc["chapters"]),
            "first_chapter_title": toc["chapters"][0]["title"] if toc["chapters"] else None,
        }

    async def _require_healthy_published_source(self, source_id: int) -> dict:
        sources = await self._source_repo.list_book_sources_full(enabled_only=True, ids=[source_id])
        if len(sources) != 1 or not bool(sources[0].get("enabled", True)):
            raise LookupError("enabled source not found")
        source = sources[0]
        snapshot = self._source_health_repo.get_snapshot(source_id)
        if snapshot is None or getattr(snapshot, "health_status", None) != "healthy":
            raise PermissionError("source must have a healthy snapshot")
        source_url = str(source.get("bookSourceUrl") or "")
        if not any(
            version.source_type == "book"
            and isinstance(version.payload, dict)
            and str(version.payload.get("bookSourceUrl") or "") == source_url
            for version in self._source_runtime_repo.list_published_versions()
        ):
            raise PermissionError("source must have a published version")
        return source

    def _canonical_chapter(self, work_id: str, chapter_index: int, title: str):
        for chapter in self._canonical_repo.list_canonical_chapters(work_id):
            if chapter.chapter_index == chapter_index:
                return chapter
        return self._canonical_repo.add_canonical_chapter(
            canonical_work_id=work_id,
            chapter_index=chapter_index,
            title=title,
        )

    @staticmethod
    def _assert_source_url(source: dict, book_url: str) -> None:
        source_host = urlparse(str(source.get("bookSourceUrl") or "")).netloc.lower()
        book_host = urlparse(book_url).netloc.lower()
        if not source_host or source_host != book_host or urlparse(book_url).scheme not in {"http", "https"}:
            raise PermissionError("book_url must belong to the selected source")

    @staticmethod
    def _content_fingerprint(content: str) -> str:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        return sha256(normalized.encode("utf-8")).hexdigest()
