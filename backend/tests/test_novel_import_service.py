from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import aiosqlite
import pytest

from app.application.services.novel_ingestion_service import NovelIngestionService
from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository
from app.services.novel_ingestion.parsers import NovelDocumentParser, UnsupportedNovelFormat
from app.services.novel_ingestion.url_security import UrlFetchResult


@pytest.fixture
async def novel_repo():
    db = await aiosqlite.connect(":memory:")
    with open("app/database_migrations/novel_schema.sql", encoding="utf-8") as schema:
        await db.executescript(schema.read())
    try:
        yield SqliteNovelRepository(db)
    finally:
        await db.close()


def test_parser_normalizes_markdown_and_splits_chapters():
    document = NovelDocumentParser().parse(
        filename="story.md",
        media_type="text/markdown",
        data="# 第一章 雨夜\n\n林远走进城门。\n\n# 第二章 清晨\n\n他开始调查。".encode(),
    )

    assert [item.title for item in document.chapters] == ["第一章 雨夜", "第二章 清晨"]
    assert document.chapters[0].text == "林远走进城门。"
    assert document.content_hash


def test_parser_supports_html_and_epub_and_rejects_unknown_format():
    html = NovelDocumentParser().parse(
        filename="story.html",
        media_type="text/html",
        data="<html><head><script>alert(1)</script></head><body><h1>第一章</h1><p>正文</p></body></html>".encode(),
    )
    assert html.chapters[0].text == "正文"

    epub_buffer = BytesIO()
    with ZipFile(epub_buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("OEBPS/chapter.xhtml", "<h1>第一章</h1><p>EPUB正文</p>")
    epub = NovelDocumentParser().parse(
        filename="story.epub",
        media_type="application/epub+zip",
        data=epub_buffer.getvalue(),
    )
    assert epub.chapters[0].text == "EPUB正文"

    with pytest.raises(UnsupportedNovelFormat):
        NovelDocumentParser().parse("story.pdf", "application/pdf", b"pdf")


@pytest.mark.asyncio
async def test_import_upload_is_idempotent_and_keeps_progress(novel_repo, tmp_path):
    service = NovelIngestionService(repo=novel_repo, source_reader=None, storage_dir=tmp_path)
    first = await service.import_upload(
        "user:1", "story.txt", "text/plain", "第1章\n正文".encode()
    )
    second = await service.import_upload(
        "user:1", "story.txt", "text/plain", "第1章\n正文".encode()
    )

    assert first.book_id == second.book_id
    assert second.duplicate is True
    assert await service.get_progress("user:1", first.book_id) is not None
    assert list(tmp_path.rglob("*"))


@pytest.mark.asyncio
async def test_import_source_delegates_to_configured_source_reader(novel_repo, tmp_path):
    class SourceReader:
        async def get_book_toc(self, source_id, book_url, **kwargs):
            return {"chapters": [{"title": "第一章", "url": "https://source.test/c1", "index": 1}]}

        async def get_chapter_content(self, source_id, chapter_url, **kwargs):
            return {"content": "来自书源的正文"}

    service = NovelIngestionService(
        repo=novel_repo, source_reader=SourceReader(), storage_dir=tmp_path
    )
    result = await service.import_source(
        "user:1", 7, "https://source.test/book", "书源小说", "作者"
    )

    assert result.status == "queued"
    chapters = await novel_repo.get_chapters_by_book("user:1", result.book_id)
    assert chapters[0].raw_text == "来自书源的正文"


@pytest.mark.asyncio
async def test_import_url_uses_validated_fetch_result(novel_repo, tmp_path):
    class Policy:
        async def fetch(self, url):
            return UrlFetchResult(
                url=url,
                content="<h1>第一章</h1><p>网络正文</p>".encode(),
                media_type="text/html",
                status_code=200,
                headers={"content-type": "text/html"},
            )

    service = NovelIngestionService(
        repo=novel_repo, storage_dir=tmp_path, url_policy=Policy()
    )
    result = await service.import_url("user:1", "https://public.test/story.html")

    assert result.status == "queued"
    chapters = await novel_repo.get_chapters_by_book("user:1", result.book_id)
    assert chapters[0].raw_text == "网络正文"
