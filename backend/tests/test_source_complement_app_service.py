import pytest


class FakeRepo:
    async def list_book_sources_full(self, enabled_only=False, ids=None, urls=None):
        return [
            {"id": 7, "bookSourceName": "源A", "bookSourceUrl": "https://a.example.com"},
            {"id": 33, "bookSourceName": "源B", "bookSourceUrl": "https://b.example.com"},
        ]


class FakeFetcher:
    async def get_content(self, source: dict, chapter_url: str):
        if source["id"] == 7:
            return {
                "title": "第一章",
                "content": "张三走进河边，看到了一具尸体。众人议论纷纷。",
                "nextUrl": "",
            }
        return {
            "title": "第一章",
            "content": "张三来到河边，发现了一具尸体。众人正在议论。",
            "nextUrl": "",
        }


@pytest.mark.asyncio
async def test_source_complement_app_service_merges_explicit_candidates():
    from app.application.services.source_complement_app_service import SourceComplementAppService

    service = SourceComplementAppService(repo=FakeRepo(), fetcher=FakeFetcher())
    result = await service.complement_chapter_candidates(
        book_name="捞尸人",
        chapter_title="第一章",
        chapter_num=1,
        items=[
            {"source_id": 7, "chapter_url": "https://a.example.com/chapter/1"},
            {"source_id": 33, "chapter_url": "https://b.example.com/chapter/1"},
        ],
    )

    assert result["book_name"] == "捞尸人"
    assert result["successful_sources"] == 2
    assert result["failed_sources"] == 0
    assert result["status"] == "success"
    assert result["final_content"]
    assert len(result["source_results"]) == 2
    assert result["merged_from"]
