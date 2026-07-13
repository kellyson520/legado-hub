import pytest

from app.infrastructure.legado.engine.http_client import HttpResponse
from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def execute_with_metadata(self, code, data=None, **kwargs):
        self.calls.append(kwargs)
        return type(
            "RuntimeOutput",
            (),
            {
                "success": True,
                "value": {
                    "request": {
                        "url": "https://a.example.com/search?wd=斗罗大陆",
                        "method": "GET",
                        "headers": {"X-Test": "1"},
                    }
                },
                "error_code": None,
                "error": None,
                "trace": None,
                "cache_updates": {},
                "compat_diff": None,
            },
        )()


class FakeHttpClient:
    async def get(self, url, headers=None, **kwargs):
        assert url == "https://a.example.com/search?wd=斗罗大陆"
        assert headers["X-Test"] == "1"
        return HttpResponse(
            url=url,
            status=200,
            text='<div class="book"><a class="title" href="/book-1">斗罗大陆</a><span class="author">唐家三少</span></div>',
            is_html=True,
        )


@pytest.mark.asyncio
async def test_fetcher_executes_js_search_url_and_parses_results():
    fetcher = LegadoBookSourceFetcher()
    fetcher._js_runtime = FakeRuntime()
    fetcher._http = FakeHttpClient()

    source = {
        "bookSourceName": "JS搜索源",
        "bookSourceUrl": "https://a.example.com",
        "searchUrl": "@js: return {request: {url: baseUrl + '/search?wd=' + variables.keyword, method: 'GET', headers: {'X-Test': '1'}}};",
        "ruleSearch": {
            "bookList": ".book",
            "name": ".title@text",
            "author": ".author@text",
            "bookUrl": ".title@href",
        },
    }

    books = await fetcher.search(source, "斗罗大陆")

    assert books[0]["name"] == "斗罗大陆"
    assert books[0]["author"] == "唐家三少"
    assert books[0]["bookUrl"] == "https://a.example.com/book-1"
    assert fetcher._js_runtime.calls[0]["stage"] == "search_url_js"


@pytest.mark.asyncio
async def test_fetcher_treats_js_search_string_as_final_get_url():
    class StringRuntime:
        def execute_with_metadata(self, code, data=None, **kwargs):
            return type(
                "RuntimeOutput",
                (),
                {
                    "success": True,
                    "value": "https://a.example.com/search?wd=斗罗大陆",
                    "error_code": None,
                    "error": None,
                    "trace": None,
                    "cache_updates": {},
                    "compat_diff": None,
                },
            )()

    class FakeHttp:
        async def get(self, url, headers=None, **kwargs):
            assert url == "https://a.example.com/search?wd=斗罗大陆"
            return HttpResponse(
                url=url,
                status=200,
                text='<div class="book"><a class="title" href="/book-2">斗罗大陆</a><span class="author">唐家三少</span></div>',
                is_html=True,
            )

    fetcher = LegadoBookSourceFetcher()
    fetcher._js_runtime = StringRuntime()
    fetcher._http = FakeHttp()

    source = {
        "bookSourceName": "字符串JS搜索源",
        "bookSourceUrl": "https://a.example.com",
        "searchUrl": "@js: 'https://a.example.com/search?wd=斗罗大陆'",
        "ruleSearch": {
            "bookList": ".book",
            "name": ".title@text",
            "author": ".author@text",
            "bookUrl": ".title@href",
        },
    }

    books = await fetcher.search(source, "斗罗大陆")

    assert books[0]["name"] == "斗罗大陆"
    assert books[0]["bookUrl"] == "https://a.example.com/book-2"


@pytest.mark.asyncio
async def test_fetcher_treats_js_search_string_plus_json_as_request_spec():
    class StringRuntime:
        def execute_with_metadata(self, code, data=None, **kwargs):
            return type(
                "RuntimeOutput",
                (),
                {
                    "success": True,
                    "value": 'https://a.example.com/search,{"method":"POST","body":{"keyword":"斗罗大陆"}}',
                    "error_code": None,
                    "error": None,
                    "trace": None,
                    "cache_updates": {},
                    "compat_diff": None,
                },
            )()

    class FakeHttp:
        async def post(self, url, data=None, json_data=None, headers=None, **kwargs):
            assert url == "https://a.example.com/search"
            assert json_data == {"keyword": "斗罗大陆"}
            return HttpResponse(
                url=url,
                status=200,
                json_data={
                    "data": [
                        {"name": "斗罗大陆", "author": "唐家三少", "bookUrl": "/book-3"}
                    ]
                },
                is_json=True,
            )

    fetcher = LegadoBookSourceFetcher()
    fetcher._js_runtime = StringRuntime()
    fetcher._http = FakeHttp()

    source = {
        "bookSourceName": "请求串JS搜索源",
        "bookSourceUrl": "https://a.example.com",
        "searchUrl": "@js: url+'search,'+JSON.stringify(option)",
        "ruleSearch": {
            "bookList": "$.data[*]",
            "name": "name",
            "author": "author",
            "bookUrl": "bookUrl",
        },
    }

    books = await fetcher.search(source, "斗罗大陆")

    assert books[0]["name"] == "斗罗大陆"
    assert books[0]["author"] == "唐家三少"
    assert books[0]["bookUrl"] == "https://a.example.com/book-3"


@pytest.mark.asyncio
async def test_fetcher_treats_relative_js_search_string_plus_json_as_request_spec():
    class StringRuntime:
        def execute_with_metadata(self, code, data=None, **kwargs):
            return type(
                "RuntimeOutput",
                (),
                {
                    "success": True,
                    "value": '/search,{"method":"POST","body":"keyword=斗罗大陆"}',
                    "error_code": None,
                    "error": None,
                    "trace": None,
                    "cache_updates": {},
                    "compat_diff": None,
                },
            )()

    class FakeHttp:
        async def post(self, url, data=None, json_data=None, headers=None, **kwargs):
            assert url == "https://a.example.com/search"
            assert data == "keyword=斗罗大陆"
            return HttpResponse(
                url=url,
                status=200,
                json_data={
                    "data": [
                        {"name": "斗罗大陆", "author": "唐家三少", "bookUrl": "/book-4"}
                    ]
                },
                is_json=True,
            )

    fetcher = LegadoBookSourceFetcher()
    fetcher._js_runtime = StringRuntime()
    fetcher._http = FakeHttp()

    source = {
        "bookSourceName": "相对请求串JS搜索源",
        "bookSourceUrl": "https://a.example.com",
        "searchUrl": "@js: '/search,'+JSON.stringify(option)",
        "ruleSearch": {
            "bookList": "$.data[*]",
            "name": "name",
            "author": "author",
            "bookUrl": "bookUrl",
        },
    }

    books = await fetcher.search(source, "斗罗大陆")

    assert books[0]["name"] == "斗罗大陆"
    assert books[0]["bookUrl"] == "https://a.example.com/book-4"


@pytest.mark.asyncio
async def test_fetcher_uses_raw_key_for_prefix_sensitive_js_search_rules():
    class PrefixRuntime:
        def __init__(self):
            self.calls = []

        def execute_with_metadata(self, code, data=None, **kwargs):
            self.calls.append(kwargs)
            return type(
                "RuntimeOutput",
                (),
                {
                    "success": True,
                    "value": {"response": {"data": {"posts": [{"title": "斗罗大陆", "url": "/book-raw"}]}}},
                    "error_code": None,
                    "error": None,
                    "trace": None,
                    "cache_updates": {},
                    "compat_diff": None,
                },
            )()

    fetcher = LegadoBookSourceFetcher()
    runtime = PrefixRuntime()
    fetcher._js_runtime = runtime
    source = {
        "bookSourceName": "prefix-search",
        "bookSourceUrl": "https://api.example.com",
        "searchUrl": "@js: let prefix = key.charAt(0); return result;",
        "ruleSearch": {
            "bookList": "$.data.posts[*]",
            "name": "$.title",
            "bookUrl": "$.url",
        },
    }

    books = await fetcher.search(source, "斗罗大陆")

    assert runtime.calls[0]["variables"]["key"] == "斗罗大陆"
    assert books[0]["bookUrl"] == "https://api.example.com/book-raw"


def test_fetcher_executes_jsonpath_then_inline_js_field_rule_with_original_item_templates():
    fetcher = LegadoBookSourceFetcher()
    item = {
        "postPageUrl": "",
        "id": 11684086064,
        "blogId": 1993354148,
    }
    rule = """$.postPageUrl
@js:
if (!result) {
  result = 'https://api.example.com/detail?post={{$.id}}&blog={{$.blogId}}';
}
"""

    value = fetcher._extract_field(
        item,
        rule,
        "https://api.example.com/newsearch/post.json",
        False,
        "bookUrl",
    )

    assert value == "https://api.example.com/detail?post=11684086064&blog=1993354148"
