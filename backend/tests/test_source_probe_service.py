import pytest


class FakeFetcher:
    async def search(self, source, keyword, page=1):
        return [{"name": keyword, "author": "唐家三少", "bookUrl": source["bookSourceUrl"] + "/book/1"}]

    async def get_toc(self, source, book_url):
        return [{"title": "第一章", "url": book_url + "/1"}]

    async def get_content(self, source, chapter_url):
        raise RuntimeError("Unexpected token '<' while decoding JSON payload")


@pytest.mark.asyncio
async def test_probe_service_collects_three_stage_evidence_and_content_failure():
    from app.application.services.source_probe_service import SourceProbeService

    source = {
        "id": 109,
        "bookSourceName": "读书阁③",
        "bookSourceUrl": "https://www.dushuge.example",
    }

    probe = await SourceProbeService(fetcher=FakeFetcher()).probe_source(
        source=source,
        keyword_samples=["斗罗大陆"],
        probe_mode="full_chain",
    )

    assert probe.search.status == "ok"
    assert probe.toc.status == "ok"
    assert probe.content.status == "failed"
    assert "Unexpected token '<'" in probe.content.error_message


@pytest.mark.asyncio
async def test_probe_service_collects_js_preflight_request_preview():
    from app.application.services.source_probe_service import SourceProbeService

    class FakeJsRuntime:
        def execute_with_metadata(self, code, data=None, **kwargs):
            return type(
                "Out",
                (),
                {
                    "success": True,
                    "value": "https://api.example.com/search?token=undefined",
                    "error": None,
                },
            )()

    class FakeFetcherWithJs:
        def __init__(self):
            self._js_runtime = FakeJsRuntime()

        @staticmethod
        def _coerce_js_search_output(value, base_url):
            return {"url": value, "method": "GET", "headers": {}}, None

        async def search(self, source, keyword, page=1):
            return []

        async def get_toc(self, source, book_url):
            return []

        async def get_content(self, source, chapter_url):
            return {"content": "", "title": "", "nextUrl": ""}

    probe = await SourceProbeService(fetcher=FakeFetcherWithJs()).probe_source(
        source={
            "id": 4,
            "bookSourceName": "起点读书限免+本章说",
            "bookSourceUrl": "https://www.qidian.com",
            "searchUrl": "@js:return 'https://api.example.com/search?token=undefined'",
        },
        keyword_samples=["捞尸人"],
        probe_mode="search_only",
    )

    assert probe.search.status == "failed"
    assert probe.search.request_preview.endswith("token=undefined")
    assert probe.search.detail["js_exec_status"] == "ok"


@pytest.mark.asyncio
async def test_probe_service_records_failed_transport_evidence_for_js_source():
    from app.application.services.source_probe_service import SourceProbeService
    from app.infrastructure.legado.engine.http_client import HttpResponse

    class FakeJsRuntime:
        def execute_with_metadata(self, code, data=None, **kwargs):
            return type(
                "Out",
                (),
                {
                    "success": True,
                    "value": "https://blocked.example.com/search?wd=test",
                    "error": None,
                },
            )()

    class FakeHttp:
        async def get(self, url, headers=None):
            return HttpResponse(
                url=url,
                status=403,
                text="<html>Just a moment...</html>",
                is_html=True,
            )

    class FakeFetcherWithTransport:
        def __init__(self):
            self._js_runtime = FakeJsRuntime()
            self._http = FakeHttp()

        @staticmethod
        def _coerce_js_search_output(value, base_url):
            return {"url": value, "method": "GET", "headers": {}}, None

        async def search(self, source, keyword, page=1):
            return []

    probe = await SourceProbeService(fetcher=FakeFetcherWithTransport()).probe_source(
        source={
            "id": 67,
            "bookSourceName": "和圖書",
            "bookSourceUrl": "https://blocked.example.com",
            "searchUrl": "@js:return 'https://blocked.example.com/search?wd=test'",
        },
        keyword_samples=["捞尸人"],
        probe_mode="search_only",
    )

    assert probe.search.detail["http_status"] == 403
    assert probe.search.detail["response_kind"] == "html"
    assert "Just a moment" in probe.search.detail["response_preview"]


@pytest.mark.asyncio
async def test_probe_service_records_toc_transport_evidence_when_directory_is_empty():
    from app.application.services.source_probe_service import SourceProbeService
    from app.infrastructure.legado.engine.http_client import HttpResponse

    class FakeFetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "bookUrl": "https://api.example.com/detail"}]

        async def get_toc(self, source, book_url):
            return []

        async def _request_configured_url(self, raw_url, headers, base_url):
            return (
                HttpResponse(
                    url=raw_url,
                    status=200,
                    is_json=True,
                    text='{"meta":{"status":4200,"msg":"用户已注销或设置仅自己可见"}}',
                ),
                raw_url,
            )

    probe = await SourceProbeService(fetcher=FakeFetcher()).probe_source(
        source={
            "id": 108,
            "bookSourceName": "Lofter",
            "bookSourceUrl": "https://api.example.com",
        },
        keyword_samples=["捞尸人"],
        probe_mode="full_chain",
    )

    assert probe.toc.status == "failed"
    assert probe.toc.detail["http_status"] == 200
    assert probe.toc.detail["response_kind"] == "json"
    assert probe.toc.detail["expected_response_kind"] == "json"
    assert probe.toc.detail["parse_status"] == "empty"


@pytest.mark.asyncio
async def test_content_verification_shell_is_classified_as_access_blocked():
    from app.application.services.source_probe_service import SourceProbeService
    from app.infrastructure.legado.engine.http_client import HttpResponse

    class VerificationWallFetcher:
        async def search(self, source, keyword, page=1):
            return [{'name': keyword, 'bookUrl': 'https://www.bqgiu.cc/book/66/'}]

        async def get_toc(self, source, book_url):
            return [{'title': 'Chapter 1', 'url': 'https://www.bqgiu.cc/book/66/1.html'}]

        async def get_content(self, source, chapter_url):
            return {'content': '', 'title': '', 'nextUrl': ''}

        async def _request_configured_url(self, raw_url, headers, base_url):
            return HttpResponse(
                url='https://www.bqgiu.cc/user/verify.html#/book/66/1.html',
                status=200,
                is_html=True,
                text='<title>loading</title><script>getCookie("getsite")</script>',
            ), raw_url

    evidence = await SourceProbeService(fetcher=VerificationWallFetcher()).probe_source(
        {'id': 1, 'bookSourceName': 'bqgiu', 'bookSourceUrl': 'https://www.bqgiu.cc/'},
        ['novel'], probe_mode='full_chain',
    )

    assert evidence.content.detail['block_reason'] == 'verification_wall'
    assert evidence.content.detail['parse_status'] == 'content_access_blocked'
