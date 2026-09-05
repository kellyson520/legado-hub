from dataclasses import dataclass

import pytest

from app.application.services.novel_ingestion.parsers import EmptyNovelDocument, NovelDocumentParser, ParsedNovelDocument
from app.application.services.novel_ingestion.quality import build_import_preview
from app.application.services.novel_ingestion_service import NovelIngestionService


@dataclass
class FakeRepo:
    save_calls: int = 0


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


def test_empty_upload_error_contract_is_explicit():
    with pytest.raises(EmptyNovelDocument) as error:
        NovelDocumentParser().parse("empty.txt", "text/plain", b"")

    assert error.value.code == "empty_document"
