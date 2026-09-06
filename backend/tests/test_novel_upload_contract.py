from dataclasses import dataclass

import pytest

from app.application.services.novel_ingestion.parsers import EmptyNovelDocument, NovelDocumentParser, ParsedNovelDocument
from app.application.services.novel_ingestion.quality import build_import_preview
from app.application.services.novel_ingestion_service import NovelIngestionService


class FakeCanonicalRepo:
    def __init__(self):
        self.work_calls = []
        self.chapter_calls = []
        self.source_work_calls = []
        self.source_chapter_calls = []
        self.variant_calls = []

    def create_canonical_work(self, **kwargs):
        self.work_calls.append(kwargs)
        return type("Work", (), {"id": "work-1"})()

    def add_alias(self, *args, **kwargs):
        pass

    def list_canonical_chapters(self, work_id):
        return []

    def add_canonical_chapter(self, **kwargs):
        self.chapter_calls.append(kwargs)
        return type("Chapter", (), {"id": f"chapter-{len(self.chapter_calls)}"})()

    def create_source_work(self, **kwargs):
        self.source_work_calls.append(kwargs)
        return type("SourceWork", (), {"id": "source-work-1"})()

    def add_source_chapter(self, **kwargs):
        self.source_chapter_calls.append(kwargs)
        return type("SourceChapter", (), {"id": f"source-chapter-{len(self.source_chapter_calls)}"})()

    def add_content_variant(self, **kwargs):
        self.variant_calls.append(kwargs)
        return type("Variant", (), {"id": f"variant-{len(self.variant_calls)}"})()
from app.application.services.novel_ingestion.upload_limits import MAX_UPLOAD_BYTES, _read_upload_bytes


@dataclass
class FakeRepo:
    save_calls: int = 0
    books: list = None

    def __post_init__(self):
        self.books = []

    async def get_book_by_url(self, *args):
        return None

    async def save_book(self, owner_scope, book):
        book.id = len(self.books) + 1
        self.books.append(book)
        return book

    async def save_chapters_batch(self, owner_scope, chapters):
        self.save_calls += len(chapters)
        for index, chapter in enumerate(chapters, 1):
            chapter.id = index
        return len(chapters)

    async def save_reading_progress(self, progress):
        return progress

    async def update_book_status(self, *args, **kwargs):
        return None

    async def get_chapters_by_book(self, *args, **kwargs):
        return []

    async def get_reading_progress(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_import_document_mirrors_uploaded_chapters_to_canonical_store():
    repo = FakeRepo()
    canonical = FakeCanonicalRepo()
    service = NovelIngestionService(repo, runtime_repo=None)
    service._canonical_repo = canonical
    document = NovelDocumentParser().parse("book.txt", "text/plain", "第一章\n足够长的章节内容".encode())
    result = await service.import_document(
        "tenant", document, filename="book.txt", media_type="text/plain", data=b"raw"
    )
    assert result.book_id > 0
    assert canonical.work_calls
    assert len(canonical.variant_calls) == len(document.chapters)


@pytest.mark.asyncio
async def test_import_document_mirrors_existing_complete_book(monkeypatch):
    repo = FakeRepo()
    document = NovelDocumentParser().parse("book.txt", "text/plain", "第一章\n足够长的章节内容".encode())
    book = type("Book", (), {"id": 1})()
    async def get_book_by_url(*args):
        return book

    async def get_chapters_by_book(*args, **kwargs):
        return [type("Chapter", (), {"id": 1})()]

    repo.get_book_by_url = get_book_by_url
    repo.get_chapters_by_book = get_chapters_by_book
    service = NovelIngestionService(repo)
    mirrored = []
    async def mirror(*args, **kwargs):
        mirrored.append(True)

    service._mirror_to_canonical = mirror
    result = await service.import_document(
        "tenant", document, filename="book.txt", media_type="text/plain", data=b"raw"
    )
    assert result.duplicate is True
    assert mirrored == [True]


@pytest.mark.asyncio
async def test_import_upload_prepares_document_once_and_reuses_it(monkeypatch):
    service = NovelIngestionService(FakeRepo())
    document = NovelDocumentParser().parse("book.txt", "text/plain", "第一章\n足够长的章节内容".encode())
    calls = []

    async def prepare(*args, **kwargs):
        calls.append(True)
        return document, build_import_preview(document)

    async def save(*args, **kwargs):
        assert args[1] is document
        return "saved"

    monkeypatch.setattr(service, "prepare_upload", prepare)
    monkeypatch.setattr(service, "import_document", save)

    result = await service.import_upload("tenant", "book.txt", "text/plain", b"ignored")

    assert result == "saved"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_upload_reader_rejects_payload_over_limit():
    class OversizedUpload:
        async def read(self, size=-1):
            return b"x" * (MAX_UPLOAD_BYTES + 1)

    with pytest.raises(Exception) as error:
        await _read_upload_bytes(OversizedUpload())

    assert error.value.code == "upload_too_large"


def test_upload_limit_accepts_supplied_novel_files():
    from pathlib import Path

    largest = max(Path("/txt").glob("*.txt"), key=lambda item: item.stat().st_size)
    assert MAX_UPLOAD_BYTES >= largest.stat().st_size


def test_empty_upload_error_contract_is_explicit():
    with pytest.raises(EmptyNovelDocument) as error:
        NovelDocumentParser().parse("empty.txt", "text/plain", b"")

    assert error.value.code == "empty_document"
