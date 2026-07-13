import pytest


class FakeFetcher:
    async def search(self, source: dict, keyword: str, page: int = 1):
        return [
            {
                "name": keyword,
                "author": "测试作者",
                "bookUrl": source["bookSourceUrl"] + "/book/1",
                "sourceName": source["bookSourceName"],
                "sourceUrl": source["bookSourceUrl"],
                "_source_config": source,
            }
        ]

    async def get_toc(self, source: dict, book_url: str):
        return [{"title": "第一章 入世", "url": book_url + "/1"}]

    async def get_content(self, source: dict, chapter_url: str):
        return {"content": "这是正文内容。", "title": "第一章 入世", "nextUrl": ""}


@pytest.mark.asyncio
async def test_source_read_service_runs_search_toc_and_content():
    from app.application.services.source_read_service import SourceReadService

    class FakeRepo:
        async def list_book_sources_full(self, enabled_only=False, ids=None, urls=None):
            return [
                {
                    "id": 1,
                    "bookSourceName": "测试源A",
                    "bookSourceUrl": "https://a.example.com",
                    "enabled": True,
                    "searchUrl": "https://a.example.com/search?key={{key}}",
                    "ruleSearch": {"bookList": ".book", "name": ".title", "bookUrl": "a@href"},
                    "ruleToc": {"chapterList": "#list a", "chapterName": "text", "chapterUrl": "href"},
                    "ruleContent": {"content": "#content"},
                }
            ]

    service = SourceReadService(repo=FakeRepo(), fetcher=FakeFetcher())
    results = await service.search_books(keyword="捞尸人")

    assert results["items"][0]["name"] == "捞尸人"
    book = await service.get_book_toc(source_id=1, book_url="https://a.example.com/book/1")
    assert book["chapters"][0]["title"] == "第一章 入世"
    chapter = await service.get_chapter_content(source_id=1, chapter_url="https://a.example.com/book/1/1")
    assert chapter["content"] == "这是正文内容。"


@pytest.mark.asyncio
async def test_source_read_service_prefers_author_hint_when_results_share_title():
    from app.application.services.source_read_service import SourceReadService

    class Repo:
        async def list_book_sources_full(self, enabled_only=False, ids=None, urls=None):
            return [
                {
                    "id": 7,
                    "bookSourceName": "测试源",
                    "bookSourceUrl": "https://a.example.com",
                    "enabled": True,
                }
            ]

    class Fetcher:
        async def search(self, source: dict, keyword: str, page: int = 1):
            return [
                {"name": keyword, "author": "甲作者", "bookUrl": "https://a.example.com/book/1"},
                {"name": keyword, "author": "乙作者", "bookUrl": "https://a.example.com/book/2"},
                {"name": keyword + "番外", "author": "乙作者", "bookUrl": "https://a.example.com/book/3"},
            ]

    service = SourceReadService(repo=Repo(), fetcher=Fetcher())
    result = await service.search_books(
        keyword="斗罗大陆",
        source_ids=[7],
        limit_per_source=2,
        author_hint="乙作者",
    )

    assert result["items"][0]["author"] == "乙作者"
    assert result["items"][0]["name"] == "斗罗大陆"


def test_factory_builds_source_read_service(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-read-factory.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.factory import build_source_read_service

    service = build_source_read_service()
    assert service is not None


@pytest.mark.asyncio
async def test_source_read_service_returns_route_summary_and_health_fields():
    from app.application.services.source_read_service import SourceReadService

    class Repo:
        async def list_book_sources_full(self, enabled_only=False, ids=None, urls=None):
            return [
                {
                    "id": 1,
                    "bookSourceName": "Healthy",
                    "bookSourceUrl": "https://a.example.com",
                    "enabled": True,
                    "searchUrl": "https://a.example.com/search?key={{key}}",
                },
                {
                    "id": 2,
                    "bookSourceName": "Blocked",
                    "bookSourceUrl": "https://b.example.com",
                    "enabled": True,
                    "searchUrl": "@js:return 'https://b.example.com'",
                },
            ]

    class Fetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "author": "唐家三少", "bookUrl": source["bookSourceUrl"] + "/book/1"}]

    class RoutingService:
        def rank_search_sources(self, sources, snapshots, routing_mode="auto"):
            return [
                {
                    "source": sources[0],
                    "decision": {
                        "route_decision": "allow",
                        "health_status": "healthy",
                        "failure_reason": "",
                        "route_score": 100,
                    },
                }
            ]

        def snapshot_map(self, source_ids):
            return {1: None, 2: None}

    service = SourceReadService(repo=Repo(), fetcher=Fetcher(), routing_service=RoutingService())
    result = await service.search_books(keyword="斗罗大陆", include_health=True, routing_mode="auto")

    assert result["items"][0]["health_status"] == "healthy"
    assert result["route_summary"]["selected_source_ids"] == [1]


@pytest.mark.asyncio
async def test_get_book_toc_falls_back_to_alternate_source_when_primary_is_blocked():
    from app.application.services.source_read_service import SourceReadService

    class Repo:
        async def list_book_sources_full(self, enabled_only=False, ids=None, urls=None):
            all_sources = [
                {"id": 1, "bookSourceName": "Primary", "bookSourceUrl": "https://a.example.com", "enabled": True},
                {"id": 2, "bookSourceName": "Fallback", "bookSourceUrl": "https://b.example.com", "enabled": True},
            ]
            return [item for item in all_sources if ids is None or item["id"] in ids]

    class Fetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "author": "唐家三少", "bookUrl": source["bookSourceUrl"] + "/book/1"}]

        async def get_toc(self, source, book_url):
            if source["id"] == 1:
                return []
            return [{"title": "第一章 入世", "url": book_url + "/1"}]

        async def get_content(self, source, chapter_url):
            return {"content": "正文", "title": "第一章 入世", "nextUrl": ""}

    class RoutingService:
        def snapshot_map(self, source_ids):
            return {
                1: type("Snap", (), {"health_status": "blocked", "failure_reason": "waf_blocked", "route_policy": "skip", "route_score": 0})(),
                2: type("Snap", (), {"health_status": "healthy", "failure_reason": "", "route_policy": "allow", "route_score": 100})(),
            }

        def rank_search_sources(self, sources, snapshots, routing_mode="auto"):
            return [
                {
                    "source": sources[1],
                    "decision": {
                        "health_status": "healthy",
                        "failure_reason": "",
                        "route_decision": "allow",
                        "route_score": 100,
                    },
                }
            ]

    service = SourceReadService(repo=Repo(), fetcher=Fetcher(), routing_service=RoutingService())
    result = await service.get_book_toc(
        source_id=1,
        book_url="https://a.example.com/book/1",
        book_name="斗罗大陆",
        author_hint="唐家三少",
        routing_mode="auto",
    )

    assert result["resolved_source_id"] == 2
    assert result["fallback_used"] is True
    assert result["chapters"][0]["title"] == "第一章 入世"


@pytest.mark.asyncio
async def test_get_chapter_content_falls_back_by_chapter_index():
    from app.application.services.source_read_service import SourceReadService

    class Repo:
        async def list_book_sources_full(self, enabled_only=False, ids=None, urls=None):
            all_sources = [
                {"id": 1, "bookSourceName": "Primary", "bookSourceUrl": "https://a.example.com", "enabled": True},
                {"id": 2, "bookSourceName": "Fallback", "bookSourceUrl": "https://b.example.com", "enabled": True},
            ]
            return [item for item in all_sources if ids is None or item["id"] in ids]

    class Fetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "author": "南派三叔", "bookUrl": source["bookSourceUrl"] + "/book/1"}]

        async def get_toc(self, source, book_url):
            return [
                {"title": "第一章 出发", "url": book_url + "/1", "index": 0},
                {"title": "第二章 夜路", "url": book_url + "/2", "index": 1},
            ]

        async def get_content(self, source, chapter_url):
            if source["id"] == 1:
                return {"content": "", "title": "第二章 夜路", "nextUrl": ""}
            return {"content": "补源正文", "title": "第二章 夜路", "nextUrl": ""}

    class RoutingService:
        def snapshot_map(self, source_ids):
            return {
                1: type("Snap", (), {"health_status": "degraded", "failure_reason": "parse_empty", "route_policy": "deprioritize", "route_score": 30})(),
                2: type("Snap", (), {"health_status": "healthy", "failure_reason": "", "route_policy": "allow", "route_score": 100})(),
            }

        def rank_search_sources(self, sources, snapshots, routing_mode="auto"):
            return [
                {
                    "source": sources[1],
                    "decision": {
                        "health_status": "healthy",
                        "failure_reason": "",
                        "route_decision": "allow",
                        "route_score": 100,
                    },
                }
            ]

    service = SourceReadService(repo=Repo(), fetcher=Fetcher(), routing_service=RoutingService())
    result = await service.get_chapter_content(
        source_id=1,
        chapter_url="https://a.example.com/book/1/2",
        book_name="捞尸人",
        author_hint="南派三叔",
        chapter_title="第二章 夜路",
        chapter_index=1,
        routing_mode="auto",
    )

    assert result["resolved_source_id"] == 2
    assert result["fallback_used"] is True
    assert result["content"] == "补源正文"
