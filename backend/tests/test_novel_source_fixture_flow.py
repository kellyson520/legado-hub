import pytest

from app.application.services.source_read_service import SourceReadService


class FixtureFetcher:
    async def search(self, source, keyword, page=1):
        assert keyword == "星河"
        return [{"name": "星河纪事", "author": "林默", "bookUrl": "https://fixture.invalid/book/1"}]

    async def get_toc(self, source, book_url):
        return [
            {"index": 1, "title": "第一章 雨夜", "url": "https://fixture.invalid/chapter/1"},
            {"index": 2, "title": "第二章 重逢", "url": "https://fixture.invalid/chapter/2"},
        ]

    async def get_content(self, source, chapter_url):
        return {
            "title": "第一章 雨夜" if chapter_url.endswith("/1") else "第二章 重逢",
            "content": "林默在子时抵达长安。" if chapter_url.endswith("/1") else "三天后，林默与苏晚重逢。",
            "next_url": "",
        }


class EmptyRepo:
    async def list_book_sources_full(self, *, enabled_only=False, ids=None, urls=None):
        return []


class FixtureRepo:
    async def list_book_sources_full(self, *, enabled_only=False, ids=None, urls=None):
        return [{
            "id": 7,
            "bookSourceName": "fixture-source",
            "bookSourceUrl": "https://fixture.invalid",
            "enabled": True,
        }]


@pytest.mark.asyncio
async def test_source_search_rejects_empty_runtime_source_inventory():
    service = SourceReadService(EmptyRepo(), FixtureFetcher())
    with pytest.raises(Exception) as error:
        await service.search_books("星河")
    assert getattr(error.value, "code", None) == "SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_source_search_toc_and_chapter_download_flow_is_deterministic():
    service = SourceReadService(FixtureRepo(), FixtureFetcher())
    search = await service.search_books("星河", source_ids=[7], limit_per_source=3)
    assert search["items"][0]["name"] == "星河纪事"

    toc = await service.get_book_toc(7, "https://fixture.invalid/book/1")
    assert [item["title"] for item in toc["chapters"]] == ["第一章 雨夜", "第二章 重逢"]

    chapter = await service.get_chapter_content(7, toc["chapters"][0]["url"])
    assert "林默" in chapter["content"]
    assert chapter["fallback_used"] is False
