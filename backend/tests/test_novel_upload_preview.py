from dataclasses import dataclass

import pytest

from app.application.services.novel_ingestion_service import NovelIngestionService


@dataclass
class FakeRepo:
    save_calls: int = 0


@pytest.mark.asyncio
async def test_preview_upload_does_not_persist_and_returns_quality_summary():
    service = NovelIngestionService(FakeRepo())

    preview = await service.preview_upload(
        "user:preview",
        "book.txt",
        "text/plain",
        "正文内容，没有章节标题".encode(),
    )

    assert preview.content_hash
    assert len(preview.chapters) == 1
    assert any(item.code == "no_heading_detected" for item in preview.warnings)
    assert service._repo.save_calls == 0


@pytest.mark.asyncio
async def test_preview_upload_rejects_empty_document():
    service = NovelIngestionService(FakeRepo())

    with pytest.raises(ValueError, match="empty"):
        await service.preview_upload("user:preview", "empty.txt", "text/plain", b"")
