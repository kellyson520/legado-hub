import shutil

import pytest

import app.infrastructure.legado.engine.js_runtime as js_runtime_module
from app.infrastructure.legado.engine.js_runtime import JsRuntime


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bridge tests")


def test_js_runtime_java_get_bridge_reads_remote_payload():
    class BridgeRuntime(JsRuntime):
        def _handle_bridge_http(self, request_spec):
            assert request_spec["url"] == "https://api.example.com/search?wd=斗罗大陆"
            return {"status": 200, "text": '{"items":[{"name":"斗罗大陆"}]}'}

    runtime = BridgeRuntime()
    output = runtime.execute_with_metadata(
        "return JSON.parse(await java.get('https://api.example.com/search?wd=斗罗大陆')).items[0].name;",
        stage="search_url_js",
        source={"bookSourceName": "bridge-test", "bookSourceUrl": "https://api.example.com"},
        baseUrl="https://api.example.com",
    )

    assert output.success is True
    assert output.value == "斗罗大陆"


def test_js_runtime_can_delegate_bridge_to_platform_runtime_bridge():
    class PlatformBridge:
        def __init__(self):
            self.calls = []

        def handle(self, request):
            self.calls.append(request)
            return {"status": 200, "text": "platform", "headers": {}}

    bridge = PlatformBridge()
    runtime = JsRuntime(runtime_bridge=bridge)
    try:
        response = runtime._handle_bridge_http({"method": "GET", "url": "https://example.test"})
        assert response["text"] == "platform"
        assert bridge.calls == [{"method": "GET", "url": "https://example.test"}]
    finally:
        runtime.close()


def test_java_ajax_response_wrapper_exposes_string_methods():
    class BridgeRuntime(JsRuntime):
        def _handle_bridge_http(self, request_spec):
            return {
                "status": 200,
                "text": '<input type="hidden" name="_token" value="token-xyz" />',
                "headers": {},
            }

    runtime = BridgeRuntime()
    output = runtime.execute_with_metadata(
        """
        var html = java.ajax('https://example.com/check');
        var token = html.match(/name="_token" value="(.+?)"/);
        return token[1];
        """,
        stage="search_url_js",
        source={"bookSourceName": "string-wrapper", "bookSourceUrl": "https://example.com"},
        baseUrl="https://example.com",
        variables={},
    )

    assert output.success is True
    assert output.value == "token-xyz"


def test_js_runtime_handles_multiline_final_expression_without_explicit_return():
    class BridgeRuntime(JsRuntime):
        def _handle_bridge_http(self, request_spec):
            return {
                "status": 200,
                "text": '<input type="hidden" name="_token" value="token-xyz" />',
                "headers": {},
            }

    runtime = BridgeRuntime()
    output = runtime.execute_with_metadata(
        """
        html = java.ajax(source.getKey())
        token = org.jsoup.Jsoup.parse(html).select('input[name=_token]').attr('value')
        "/search,"+JSON.stringify({
          "body": `_token=${token}&kw=${key}`,
          "method": "POST"
        })
        """,
        stage="search_url_js",
        source={"bookSourceName": "multiline-tail", "bookSourceUrl": "https://example.com"},
        baseUrl="https://example.com",
        variables={"key": "斗罗大陆"},
    )

    assert output.success is True
    assert output.value == '/search,{"body":"_token=token-xyz&kw=斗罗大陆","method":"POST"}'


def test_js_runtime_supports_switch_block_without_explicit_return():
    runtime = JsRuntime()
    output = runtime.execute_with_metadata(
        """
        let prefix = key.charAt(0);
        switch(prefix) {
            case '#':
                result = 'tag-search';
                break;
            default:
                result = 'post-search';
        }
        """,
        stage="search_url_js",
        source={"bookSourceName": "switch-block", "bookSourceUrl": "https://example.com"},
        baseUrl="https://example.com",
        variables={"key": "斗罗大陆"},
    )

    assert output.success is True
    assert output.value == "post-search"


def test_js_runtime_exposes_source_helpers_and_variable_aliases():
    runtime = JsRuntime()
    output = runtime.execute_with_metadata(
        """
        return {
          keyAlias: key,
          pageAlias: page,
          token: source.get('cdkey'),
          loginToken: source.getLoginInfoMap().get('cdkey')
        };
        """,
        stage="search_url_js",
        source={
            "bookSourceName": "helper-test",
            "bookSourceUrl": "https://api.example.com",
            "cdkey": "token-abc",
        },
        baseUrl="https://api.example.com",
        variables={"key": "斗罗大陆", "page": 3},
    )

    assert output.success is True
    assert output.value["keyAlias"] == "斗罗大陆"
    assert output.value["pageAlias"] == 3
    assert output.value["token"] == "token-abc"
    assert output.value["loginToken"] == "token-abc"


def test_js_runtime_java_get_wrapper_supports_header_lookup_without_explicit_await():
    class BridgeRuntime(JsRuntime):
        def _handle_bridge_http(self, request_spec):
            assert request_spec["method"] == "GET"
            assert "斗罗大陆" in request_spec["url"]
            assert request_spec["follow_redirects"] is False
            return {
                "status": 302,
                "text": "",
                "headers": {"location": "result.php?searchid=77&"},
            }

    runtime = BridgeRuntime()
    output = runtime.execute_with_metadata(
        """
        let new_url = java.get('https://www.8xsk.info/e/search/index.php?keyboard='+key+'&show=title', {
          referer: 'https://www.8xsk.info/'
        });
        let url = 'https://www.8xsk.info/e/search/' + new_url.header('location');
        url + 'page=' + page;
        """,
        stage="search_url_js",
        source={"bookSourceName": "8xsk", "bookSourceUrl": "https://www.8xsk.info"},
        baseUrl="https://www.8xsk.info",
        variables={"key": "斗罗大陆", "page": 1},
    )

    assert output.success is True
    assert output.value == "https://www.8xsk.info/e/search/result.php?searchid=77&page=1"


def test_js_runtime_java_ajax_string_config_is_parseable_without_explicit_await():
    class BridgeRuntime(JsRuntime):
        def __init__(self):
            super().__init__()
            self.calls = []

        def _handle_bridge_http(self, request_spec):
            self.calls.append(request_spec)
            if "checkUpdate" in request_spec["url"]:
                assert request_spec["method"] == "POST"
                assert request_spec["follow_redirects"] is True
                return {
                    "status": 200,
                    "text": '{"data":{"url":"api.zmtt.net/"}}',
                    "headers": {},
                }
            assert request_spec["method"] == "POST"
            assert request_spec["body"]["keyword"] == "斗罗大陆"
            return {
                "status": 200,
                "text": '{"data":[]}',
                "headers": {},
            }

    runtime = BridgeRuntime()
    output = runtime.execute_with_metadata(
        """
        option={"method":"POST","body":{"version":"2.0"}}
        url="http://"+JSON.parse(java.ajax("http://www.zmtt.net/checkUpdate,"+JSON.stringify(option))).data.url
        option={"method":"POST","body":{"keyword":key}}
        java.ajax(url+"search,"+JSON.stringify(option))
        url+"search,"+JSON.stringify(option)
        """,
        stage="search_url_js",
        source={"bookSourceName": "zmtt", "bookSourceUrl": "http://www.zmtt.net"},
        baseUrl="http://www.zmtt.net",
        variables={"key": "斗罗大陆", "page": 1},
    )

    assert output.success is True
    assert output.value.startswith("http://api.zmtt.net/search,")
    assert len(runtime.calls) == 2


def test_bridge_http_handler_returns_error_for_empty_url():
    runtime = JsRuntime()
    response = runtime._handle_bridge_http({"method": "GET", "url": ""})

    assert response["status"] == 400
    assert "empty url" in response["text"].lower()


def test_bridge_http_handler_reads_httpx_status_code(monkeypatch):
    class FakeResponse:
        status_code = 302
        text = "redirect"
        headers = {"location": "/next"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method, url, headers=None):
            return FakeResponse()

    monkeypatch.setattr(js_runtime_module.httpx, "Client", FakeClient)

    runtime = JsRuntime()
    response = runtime._handle_bridge_http(
        {"method": "GET", "url": "https://example.com", "follow_redirects": False}
    )

    assert response["status"] == 302
    assert response["headers"]["location"] == "/next"


def test_js_runtime_renders_template_markers_before_js_execution():
    runtime = JsRuntime()
    output = runtime.execute_with_metadata(
        "return 'https://example.com/search?wd={{key}}&p={{page}}';",
        stage="search_url_js",
        source={"bookSourceName": "template-test", "bookSourceUrl": "https://example.com"},
        baseUrl="https://example.com",
        variables={"key": "douluodalu", "page": 2},
    )

    assert output.success is True
    assert output.value == "https://example.com/search?wd=douluodalu&p=2"



def test_js_runtime_renders_jsonpath_template_markers_before_js_execution():
    runtime = JsRuntime()
    output = runtime.execute_with_metadata(
        "return '/book/{{$.KEYID}}?name={{$.KEYNAME}}';",
        data={"KEYID": 9527, "KEYNAME": "斗罗大陆"},
        stage="search_rule_js",
        source={"bookSourceName": "template-jsonpath", "bookSourceUrl": "https://example.com"},
        baseUrl="https://example.com",
        variables={},
    )

    assert output.success is True
    assert output.value == "/book/9527?name=斗罗大陆"


def test_js_runtime_renders_expression_templates_in_returned_string():
    runtime = JsRuntime()
    output = runtime.execute_with_metadata(
        "return 'https://example.com?q={{java.encodeURI(key)}}&first={{(page-1)*10+1}}';",
        stage="search_url_js",
        source={"bookSourceName": "expr-template", "bookSourceUrl": "https://example.com"},
        baseUrl="https://example.com",
        variables={"key": "斗罗大陆", "page": 2},
    )

    assert output.success is True
    assert output.value == "https://example.com?q=%E6%96%97%E7%BD%97%E5%A4%A7%E9%99%86&first=11"


def test_js_runtime_java_put_and_non_url_get_share_memory():
    runtime = JsRuntime()
    output = runtime.execute_with_metadata(
        """
        java.put('bid', '362918');
        return java.get('bid');
        """,
        stage="search_rule_js",
        source={"bookSourceName": "memory-test", "bookSourceUrl": "https://example.com"},
        baseUrl="https://example.com",
        variables={},
    )

    assert output.success is True
    assert output.value == "362918"


def test_js_runtime_java_get_string_reads_result_and_log_methods_are_noop():
    runtime = JsRuntime()
    output = runtime.execute_with_metadata(
        """
        java.log('debug message');
        java.longToast('toast message');
        return java.getString('$.BID');
        """,
        data={"BID": 9527},
        stage="search_rule_js",
        source={"bookSourceName": "getstring-test", "bookSourceUrl": "https://example.com"},
        baseUrl="https://example.com",
        variables={},
    )

    assert output.success is True
    assert output.value == "9527"


def test_js_runtime_supports_host_source_cookie_and_encode_uri_helpers():
    runtime = JsRuntime()
    output = runtime.execute_with_metadata(
        """
        cookie.removeCookie('https://cn.bing.com');
        return getHost() + '|' + source.getKey() + '|' + source.getVariable() + '|' + urlIP('https://mirror.example.com') + '|' + java.encodeURI('斗罗大陆');
        """,
        stage="search_url_js",
        source={
            "bookSourceName": "helper-source",
            "bookSourceUrl": "https://api.example.com",
            "key": "https://api.example.com/entry",
            "variable": "全部",
        },
        baseUrl="https://api.example.com",
        variables={},
    )

    assert output.success is True
    assert output.value == "https://api.example.com|https://api.example.com/entry|全部|https://mirror.example.com|%E6%96%97%E7%BD%97%E5%A4%A7%E9%99%86"
