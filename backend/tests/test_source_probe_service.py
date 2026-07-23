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
async def test_probe_service_includes_runtime_diagnostics_in_stage_detail():
    from app.application.services.source_probe_service import SourceProbeService

    class DiagnosticFetcher(FakeFetcher):
        def runtime_diagnostics(self):
            return {
                "mode": "native_kotlin",
                "diffs": [{"code": "NATIVE_SEMANTICS_MISMATCH", "stage": "search"}],
            }

    probe = await SourceProbeService(DiagnosticFetcher()).probe_source(
        source={"id": 3, "bookSourceUrl": "https://example.test"},
        keyword_samples=["剑来"],
        probe_mode="search_only",
    )

    assert probe.search.detail["runtime"]["mode"] == "native_kotlin"
    assert probe.search.detail["runtime"]["diffs"][0]["code"] == "NATIVE_SEMANTICS_MISMATCH"


@pytest.mark.asyncio
async def test_probe_service_falls_back_to_second_keyword_and_records_attempts():
    from app.application.services.source_probe_service import SourceProbeService

    class KeywordAwareFetcher:
        async def search(self, source, keyword, page=1):
            if keyword == "无结果关键词":
                return []
            return [{"name": keyword, "bookUrl": "https://example.test/book/1"}]

        async def get_toc(self, source, book_url):
            return [{"title": "第一章", "url": f"{book_url}/1"}]

        async def get_content(self, source, chapter_url):
            return {"title": "第一章", "content": "正文"}

    probe = await SourceProbeService(KeywordAwareFetcher()).probe_source(
        source={"id": 1, "bookSourceName": "智能书源", "bookSourceUrl": "https://example.test"},
        keyword_samples=["无结果关键词", "命中关键词"],
    )

    assert probe.keyword == "命中关键词"
    assert probe.attempted_keywords == ["无结果关键词", "命中关键词"]
    assert probe.search.status == "ok"
    assert probe.toc.status == "ok"
    assert probe.content.status == "ok"


@pytest.mark.asyncio
async def test_probe_service_keeps_trying_when_first_search_hit_breaks_full_chain():
    from app.application.services.source_probe_service import SourceProbeService

    class ChainAwareFetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "bookUrl": f"https://example.test/{keyword}"}]

        async def get_toc(self, source, book_url):
            return [{"title": "第一章", "url": f"{book_url}/1"}]

        async def get_content(self, source, chapter_url):
            return {"title": "第一章", "content": "" if "首个" in chapter_url else "有效正文"}

    probe = await SourceProbeService(ChainAwareFetcher()).probe_source(
        source={"id": 2, "bookSourceName": "链路兜底", "bookSourceUrl": "https://example.test"},
        keyword_samples=["首个关键词", "备用关键词"],
    )

    assert probe.keyword == "备用关键词"
    assert probe.attempted_keywords == ["首个关键词", "备用关键词"]
    assert probe.content.status == "ok"


@pytest.mark.asyncio
async def test_probe_service_does_not_treat_whitespace_content_as_success():
    from app.application.services.source_probe_service import SourceProbeService

    class WhitespaceContentFetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "bookUrl": "https://example.test/book/1"}]

        async def get_toc(self, source, book_url):
            return [{"title": "第一章", "url": f"{book_url}/1"}]

        async def get_content(self, source, chapter_url):
            return {"title": "第一章", "content": " \n\t "}

    probe = await SourceProbeService(WhitespaceContentFetcher()).probe_source(
        source={"id": 3, "bookSourceUrl": "https://example.test"},
        keyword_samples=["sample"],
        probe_mode="full_chain",
    )

    assert probe.content.status == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"content": "Just a moment..."},
        {"content": {"error": "captcha"}},
    ],
)
async def test_probe_service_does_not_treat_challenge_or_error_payload_as_content(
    payload,
):
    from app.application.services.source_probe_service import SourceProbeService

    class ChallengeFetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "bookUrl": "https://example.test/book/1"}]

        async def get_toc(self, source, book_url):
            return [{"title": "第一章", "url": "https://example.test/book/1/1"}]

        async def get_content(self, source, chapter_url):
            return payload

    evidence = await SourceProbeService(ChallengeFetcher()).probe_source(
        source={"id": 4, "bookSourceUrl": "https://example.test"},
        keyword_samples=["sample"],
        probe_mode="full_chain",
    )

    assert evidence.content.status == "failed"
    assert evidence.content.detail["parse_status"] in {"content_access_blocked", "error_payload"}


@pytest.mark.asyncio
async def test_probe_service_rejects_unknown_probe_mode():
    from app.application.services.source_probe_service import SourceProbeService

    with pytest.raises(ValueError, match="probe_mode"):
        await SourceProbeService(FakeFetcher()).probe_source(
            source={"id": 4, "bookSourceUrl": "https://example.test"},
            keyword_samples=["sample"],
            probe_mode="unsupported_mode",
        )


@pytest.mark.asyncio
async def test_probe_service_keeps_toc_evidence_json_serializable():
    import json

    from bs4 import BeautifulSoup

    from app.application.services.source_probe_service import SourceProbeService

    class Fetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "bookUrl": "https://example.test/book/1"}]

        async def get_toc(self, source, book_url):
            return [{
                "title": "Chapter 1",
                "url": f"{book_url}/1",
                "index": 0,
                "_raw": BeautifulSoup("<a>Chapter 1</a>", "lxml").a,
            }]

        async def get_content(self, source, chapter_url):
            return {"content": "chapter content", "title": "Chapter 1"}

    evidence = await SourceProbeService(fetcher=Fetcher()).probe_source(
        source={"id": 1, "bookSourceUrl": "https://example.test"},
        keyword_samples=["Example"],
    )

    assert evidence.toc.detail["first_chapter"] == {
        "title": "Chapter 1",
        "url": "https://example.test/book/1/1",
        "index": 0,
    }
    json.dumps(evidence.toc.detail)


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


def test_probe_service_accepts_structured_js_request_body():
    from app.application.services.source_probe_service import SourceProbeService

    class FakeJsRuntime:
        def execute_with_metadata(self, code, data=None, **kwargs):
            return type(
                "Out",
                (),
                {
                    "success": True,
                    "value": {"url": "https://api.example.com/search", "body": {"q": "捞尸人"}},
                    "error": None,
                },
            )()

    class FakeFetcherWithStructuredBody:
        def __init__(self):
            self._js_runtime = FakeJsRuntime()

        @staticmethod
        def _coerce_js_search_output(value, base_url):
            return {
                "url": value["url"],
                "method": "POST",
                "headers": {},
                "body": value["body"],
            }, None

    result = SourceProbeService(fetcher=FakeFetcherWithStructuredBody())._build_search_preflight(
        {
            "id": 4,
            "bookSourceUrl": "https://www.example.com",
            "searchUrl": "@js:return {url: 'https://api.example.com/search', body: {q: key}}",
        },
        "捞尸人",
    )

    assert result["request_preview"] == "https://api.example.com/search BODY={'q': '捞尸人'}"


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
async def test_probe_service_does_not_repeat_keywords_after_conclusive_transport_failure():
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

    class FakeFetcher:
        def __init__(self):
            self._js_runtime = FakeJsRuntime()
            self._http = FakeHttp()
            self.keywords = []

        @staticmethod
        def _coerce_js_search_output(value, base_url):
            return {"url": value, "method": "GET", "headers": {}}, None

        async def search(self, source, keyword, page=1):
            self.keywords.append(keyword)
            return []

    fetcher = FakeFetcher()
    probe = await SourceProbeService(fetcher).probe_source(
        source={
            "id": 67,
            "bookSourceName": "WAF 书源",
            "bookSourceUrl": "https://blocked.example.com",
            "searchUrl": "@js:return 'https://blocked.example.com/search?wd=test'",
        },
        keyword_samples=["捞尸人", "斗罗大陆", "剑来"],
        probe_mode="search_only",
    )

    assert fetcher.keywords == ["捞尸人"]
    assert probe.attempted_keywords == ["捞尸人"]


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
async def test_probe_service_marks_valid_empty_json_toc_as_inconclusive_result():
    from app.application.services.source_probe_service import SourceProbeService
    from app.infrastructure.legado.engine.http_client import HttpResponse

    class EmptyJsonFetcher:
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
                    text='{"data": []}',
                ),
                raw_url,
            )

    probe = await SourceProbeService(fetcher=EmptyJsonFetcher()).probe_source(
        source={
            "id": 109,
            "bookSourceName": "合法空 JSON 书源",
            "bookSourceUrl": "https://api.example.com",
        },
        keyword_samples=["捞尸人"],
        probe_mode="full_chain",
    )

    assert probe.toc.status == "failed"
    assert probe.toc.detail["parse_status"] == "empty_result"
    assert probe.toc.detail["empty_response_valid"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        "null",
        '{"success": true, "result": []}',
        '({"result": []})',
    ],
)
async def test_probe_service_accepts_common_empty_json_shapes_as_inconclusive_result(payload):
    from app.application.services.source_probe_service import SourceProbeService
    from app.infrastructure.legado.engine.http_client import HttpResponse

    class EmptyShapeFetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "bookUrl": "https://api.example.com/detail"}]

        async def get_toc(self, source, book_url):
            return []

        async def _request_configured_url(self, raw_url, headers, base_url):
            return HttpResponse(url=raw_url, status=200, is_json=True, text=payload), raw_url

    probe = await SourceProbeService(fetcher=EmptyShapeFetcher()).probe_source(
        source={"id": 117, "bookSourceName": "常见空响应书源", "bookSourceUrl": "https://api.example.com"},
        keyword_samples=["捞尸人"],
        probe_mode="full_chain",
    )

    assert probe.toc.detail["parse_status"] == "empty_result"
    assert probe.toc.detail["empty_response_valid"] is True


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


@pytest.mark.asyncio
async def test_probe_service_does_not_treat_captcha_word_in_novel_content_as_access_wall():
    from app.application.services.source_probe_service import SourceProbeService

    class NovelContentFetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "bookUrl": "https://example.test/book/1"}]

        async def get_toc(self, source, book_url):
            return [{"title": "第一章", "url": "https://example.test/book/1/1"}]

        async def get_content(self, source, chapter_url):
            return {"title": "第一章", "content": "正文提到 captcha challenge 只是一个剧情术语。"}

    evidence = await SourceProbeService(fetcher=NovelContentFetcher()).probe_source(
        source={"id": 110, "bookSourceUrl": "https://example.test"},
        keyword_samples=["sample"],
        probe_mode="full_chain",
    )

    assert evidence.content.status == "ok"
    assert "parse_status" not in evidence.content.detail


@pytest.mark.asyncio
async def test_probe_service_does_not_treat_challenge_brand_word_in_html_novel_body_as_wall():
    from app.application.services.source_probe_service import SourceProbeService

    class HtmlNovelContentFetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "bookUrl": "https://example.test/book/1"}]

        async def get_toc(self, source, book_url):
            return [{"title": "第一章", "url": "https://example.test/book/1/1"}]

        async def get_content(self, source, chapter_url):
            return {"title": "第一章", "content": "<div>正文讨论 Cloudflare 这个品牌，但不是验证页面。</div>"}

    evidence = await SourceProbeService(fetcher=HtmlNovelContentFetcher()).probe_source(
        source={"id": 113, "bookSourceUrl": "https://example.test"},
        keyword_samples=["sample"],
        probe_mode="full_chain",
    )

    assert evidence.content.status == "ok"


@pytest.mark.asyncio
async def test_probe_service_does_not_treat_captcha_challenge_words_in_html_novel_body_as_wall():
    from app.application.services.source_probe_service import SourceProbeService

    class HtmlCaptchaNovelContentFetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "bookUrl": "https://example.test/book/1"}]

        async def get_toc(self, source, book_url):
            return [{"title": "第一章", "url": "https://example.test/book/1/1"}]

        async def get_content(self, source, chapter_url):
            return {"title": "第一章", "content": "<div>正文提到 captcha challenge 只是剧情术语，不是验证页。</div>"}

    evidence = await SourceProbeService(fetcher=HtmlCaptchaNovelContentFetcher()).probe_source(
        source={"id": 116, "bookSourceUrl": "https://example.test"},
        keyword_samples=["sample"],
        probe_mode="full_chain",
    )

    assert evidence.content.status == "ok"


@pytest.mark.asyncio
async def test_probe_service_does_not_treat_verification_phrase_in_html_novel_body_as_wall():
    from app.application.services.source_probe_service import SourceProbeService

    class HtmlPhraseNovelContentFetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "bookUrl": "https://example.test/book/1"}]

        async def get_toc(self, source, book_url):
            return [{"title": "第一章", "url": "https://example.test/book/1/1"}]

        async def get_content(self, source, chapter_url):
            return {"title": "第一章", "content": "<div>角色在台词里说 verify you are human，但这是小说正文。</div>"}

    evidence = await SourceProbeService(fetcher=HtmlPhraseNovelContentFetcher()).probe_source(
        source={"id": 115, "bookSourceUrl": "https://example.test"},
        keyword_samples=["sample"],
        probe_mode="full_chain",
    )

    assert evidence.content.status == "ok"


def test_probe_service_requires_html_evidence_before_stopping_on_challenge_markers():
    from app.application.services.source_probe_service import SourceProbeService
    from app.domain.entities.source_health import SourceProbeEvidence, StageProbeResult

    evidence = SourceProbeEvidence(
        source_id=111,
        source_name="合法 JSON 元数据书源",
        source_url="https://example.test",
        probe_mode="search_only",
        keyword="sample",
        search=StageProbeResult(
            stage="search",
            status="failed",
            detail={
                "http_status": 200,
                "response_kind": "json",
                "response_preview": '{"note":"cloudflare is mentioned in metadata"}',
            },
        ),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    assert SourceProbeService._has_conclusive_transport_failure(evidence) is False

    evidence.search.detail["response_kind"] = "html"
    evidence.search.detail["response_preview"] = "<div>正文讨论 Cloudflare 这个品牌，但不是验证页面。</div>"

    assert SourceProbeService._has_conclusive_transport_failure(evidence) is False


@pytest.mark.asyncio
async def test_probe_service_keeps_uninstrumented_empty_js_stage_inconclusive():
    from app.application.services.source_probe_service import SourceProbeService

    class EmptyJsFetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "bookUrl": "https://example.test/book/1"}]

        async def get_toc(self, source, book_url):
            return []

    evidence = await SourceProbeService(fetcher=EmptyJsFetcher()).probe_source(
        source={"id": 112, "bookSourceUrl": "https://example.test"},
        keyword_samples=["sample"],
        probe_mode="full_chain",
    )

    assert evidence.toc.detail["parse_status"] == "empty_result"


@pytest.mark.asyncio
async def test_probe_service_accepts_empty_javascript_object_response_as_inconclusive():
    from app.application.services.source_probe_service import SourceProbeService
    from app.infrastructure.legado.engine.http_client import HttpResponse

    class EmptyJavascriptFetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "bookUrl": "https://example.test/book/1"}]

        async def get_toc(self, source, book_url):
            return []

        async def _request_configured_url(self, raw_url, headers, base_url):
            return HttpResponse(url=raw_url, status=200, text="({})"), raw_url

    evidence = await SourceProbeService(fetcher=EmptyJavascriptFetcher()).probe_source(
        source={"id": 114, "bookSourceUrl": "https://example.test"},
        keyword_samples=["sample"],
        probe_mode="full_chain",
    )

    assert evidence.toc.detail["parse_status"] == "empty_result"


@pytest.mark.asyncio
async def test_probe_service_synthesizes_legado_rules_from_html_search_form_and_pages():
    from app.application.services.source_probe_service import SourceProbeService

    class Response:
        def __init__(self, url, text):
            self.url = url
            self.text = text
            self.success = True
            self.is_html = True

    class FakeHttp:
        def __init__(self):
            self.posts = []

        async def get(self, url, headers=None):
            if url == 'https://example.test/':
                return Response(url, '''
                    <form method="post" action="/search.html">
                      <input type="text" name="s" />
                    </form>
                ''')
            if url == 'https://example.test/book/1':
                return Response(url, '''
                    <ul class="chapter-list">
                      <li><a href="/book/1/1">第一章</a></li>
                      <li><a href="/book/1/2">第二章</a></li>
                    </ul>
                ''')
            if url == 'https://example.test/book/1/1':
                return Response(url, '<div id="content">这是足够长的正文内容，用于确认自动写源引擎能选择正文容器。</div>')
            raise AssertionError(f'unexpected GET {url}')

        async def post(self, url, data=None, headers=None):
            self.posts.append((url, data))
            return Response(url, '''
                <ul class="result-list">
                  <li><span class="title"><a href="/book/1">斗罗大陆</a></span><span class="author">唐家三少</span></li>
                  <li><span class="title"><a href="/book/2">斗罗大陆II</a></span><span class="author">唐家三少</span></li>
                </ul>
            ''')

    class FakeFetcher:
        def __init__(self):
            self._http = FakeHttp()

    fetcher = FakeFetcher()
    rule = await SourceProbeService(fetcher=fetcher).synthesize_source_rule(
        source={
            'bookSourceUrl': 'https://example.test/',
            'bookSourceName': 'Example',
            'ruleSearch': {},
            'ruleToc': {},
            'ruleContent': {},
        },
        entry_url='https://example.test/',
        keyword='斗罗大陆',
    )

    assert fetcher._http.posts == [('https://example.test/search.html', 's=%E6%96%97%E7%BD%97%E5%A4%A7%E9%99%86')]
    assert rule['searchUrl'] == 'https://example.test/search.html::POST\ns={{key}}'
    assert rule['header'] == 'Content-Type: application/x-www-form-urlencoded'
    assert rule['ruleSearch'] == {
        'bookList': '@css:ul.result-list > li',
        'name': '@css:span.title > a@text',
        'author': '@css:span.author@text',
        'bookUrl': '@css:span.title > a@href',
    }
    assert rule['ruleToc'] == {
        'chapterList': '@css:ul.chapter-list > li > a',
        'chapterName': '@css:text',
        'chapterUrl': '@css:href',
    }
    assert rule['ruleContent']['content'] == '@css:#content@html'


def test_toc_rule_discovery_prefers_full_directory_over_latest_chapter_block():
    from bs4 import BeautifulSoup

    from app.application.services.source_probe_service import _discover_toc_rules

    rules, first_chapter_url = _discover_toc_rules(
        BeautifulSoup('''
            <div class="page">
              <ul class="section-list"><li><a href="/book/1/99">第九十九章</a></li><li><a href="/book/1/100">第一百章</a></li></ul>
              <ul class="section-list directory"><li><a href="/book/1/1">第一章</a></li><li><a href="/book/1/2">第二章</a></li><li><a href="/book/1/3">第三章</a></li></ul>
            </div>
        ''', 'lxml'),
        base_url='https://example.test/book/1',
    )

    assert rules['chapterList'] == '@css:ul.section-list.directory > li > a'
    assert first_chapter_url == 'https://example.test/book/1/1'


def test_search_rule_discovery_supports_repeated_article_cards_without_list_items():
    from bs4 import BeautifulSoup

    from app.application.services.source_probe_service import _discover_search_rules

    rules, book_url = _discover_search_rules(
        BeautifulSoup('''
            <section class="results">
              <article class="result-card"><a href="/book/1">Example Novel</a><span class="author">Author One</span></article>
              <article class="result-card"><a href="/book/2">Example Novel II</a><span class="author">Author Two</span></article>
            </section>
        ''', 'lxml'),
        keyword='Example Novel',
        base_url='https://example.test/search',
    )

    assert rules['bookList'] == '@css:section.results > article.result-card'
    assert rules['name'] == '@css:a@text'
    assert rules['bookUrl'] == '@css:a@href'
    assert book_url == 'https://example.test/book/1'


def test_toc_rule_discovery_supports_english_chapter_titles():
    from bs4 import BeautifulSoup

    from app.application.services.source_probe_service import _discover_toc_rules

    rules, chapter_url = _discover_toc_rules(
        BeautifulSoup('''
            <ol class="chapters">
              <li><a href="/book/1/chapter-1">Chapter 1</a></li>
              <li><a href="/book/1/chapter-2">Chapter 2</a></li>
            </ol>
        ''', 'lxml'),
        base_url='https://example.test/book/1',
    )

    assert rules['chapterList'] == '@css:ol.chapters > li > a'
    assert chapter_url == 'https://example.test/book/1/chapter-1'
