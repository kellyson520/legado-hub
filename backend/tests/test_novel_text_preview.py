from dataclasses import dataclass

from app.application.services.novel_ingestion.quality import build_import_preview


@dataclass(frozen=True)
class FakeChapter:
    ordinal: int
    title: str
    text: str
    content_hash: str


@dataclass(frozen=True)
class FakeDocument:
    title: str
    author: str
    normalized_text: str
    chapters: list[FakeChapter]
    content_hash: str
    media_type: str


def _chapter(ordinal, title, text, content_hash):
    return FakeChapter(ordinal, title, text, content_hash)


def _document(*chapters, title=""):
    normalized = "\n\n".join(item.text for item in chapters)
    return FakeDocument(
        title=title,
        author="",
        normalized_text=normalized,
        chapters=list(chapters),
        content_hash="document-hash",
        media_type="text/plain",
    )


def test_preview_reports_no_heading_and_chapter_summary():
    document = _document(
        _chapter(1, "book", "正文第一段\n正文第二段", "chapter-hash"),
        title="book",
    )

    preview = build_import_preview(document)

    assert len(preview.chapters) == 1
    assert any(item.code == "no_heading_detected" for item in preview.warnings)
    assert preview.chapters[0]["word_count"] > 0
    assert preview.chapters[0]["content_hash"] == "chapter-hash"


def test_preview_reports_short_chapters_without_rejecting_document():
    document = _document(
        _chapter(1, "第一章", "短", "short-hash"),
        _chapter(2, "第二章", "这是足够长的章节内容", "long-hash"),
    )

    preview = build_import_preview(document, min_chapter_chars=5)

    assert len(preview.chapters) == 2
    assert any(item.code == "short_chapter" and item.chapter_index == 1 for item in preview.warnings)


def test_parser_supports_blank_line_split_mode():
    from app.application.services.novel_ingestion.parsers import NovelDocumentParser

    document = NovelDocumentParser().parse(
        "book.txt",
        "text/plain",
        "第一段内容\n\n第二段内容".encode(),
        split_mode="blank-line",
    )

    assert [chapter.text for chapter in document.chapters] == ["第一段内容", "第二段内容"]


def test_parser_supports_fixed_size_split_mode():
    from app.application.services.novel_ingestion.parsers import NovelDocumentParser

    document = NovelDocumentParser().parse(
        "book.txt",
        "text/plain",
        "abcdefghij".encode(),
        split_mode="fixed-size",
        fixed_size=4,
    )

    assert [chapter.text for chapter in document.chapters] == ["abcd", "efgh", "ij"]


def test_parser_rejects_unknown_split_mode():
    from app.application.services.novel_ingestion.parsers import NovelDocumentParser, NovelImportError

    try:
        NovelDocumentParser().parse("book.txt", "text/plain", b"content", split_mode="unknown")
    except NovelImportError as error:
        assert error.code == "invalid_split_mode"
    else:
        raise AssertionError("unknown split mode must be rejected")


def test_preview_reports_too_many_chapters_with_bounded_summary():
    document = _document(
        *[
            _chapter(index, f"第{index}章", f"内容 {index}", f"hash-{index}")
            for index in range(1, 4)
        ],
    )

    preview = build_import_preview(document, max_chapters=2)

    assert len(preview.chapters) == 2
    assert any(item.code == "too_many_chapters" for item in preview.warnings)
