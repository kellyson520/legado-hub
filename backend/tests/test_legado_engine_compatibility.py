from app.infrastructure.legado.engine import JsonPathExt, JsRuntime, RuleSelector, RuleType


def test_engine_exports_legacy_symbols():
    assert RuleType.JSONPATH == "jsonpath"
    assert RuleType.CSS == "css"
    assert RuleType.XPATH == "xpath"


def test_jsonpath_ext_supports_fallback_regex_and_template():
    data = {
        "data": {
            "items": [{"name": "斗罗大陆"}, {"name": "捞尸人"}],
            "total": 2,
        },
        "message": "success",
    }

    assert JsonPathExt.query(data, "$.data.total") == 2
    assert JsonPathExt.query(data, "$.missing||$.message") == "success"
    assert JsonPathExt.query(data, "$.data.items[*].name") == ["斗罗大陆", "捞尸人"]
    assert JsonPathExt.query(data, "$.data.items[*].name##大陆|人") == ["斗罗", "捞尸"]
    assert JsonPathExt.fill_template("/books/{{$.data.items[0].name}}?total={{$.data.total}}", data) == "/books/斗罗大陆?total=2"


def test_jsonpath_ext_template_supports_cache_lookup():
    data = {"chapterid": 657077}
    rendered = JsonPathExt.fill_template(
        "https://novel.cooks.tw/api/chapter/content/{{cache.getFromMemory('articleid')}}/{{$.chapterid}}?lang=zh-CN",
        data,
        extra_vars={"cache": {"articleid": 362918}},
    )
    assert rendered == "https://novel.cooks.tw/api/chapter/content/362918/657077?lang=zh-CN"


def test_rule_selector_extracts_html_shorthand_list_and_fields():
    html = """
    <div class="bookbox">
      <a href="/cover-1">cover</a>
      <a href="/book-1">斗罗大陆</a>
      <div class="author">唐家三少</div>
    </div>
    <div class="bookbox">
      <a href="/cover-2">cover</a>
      <a href="/book-2">捞尸人</a>
      <div class="author">纯洁滴小龙</div>
    </div>
    """

    items = RuleSelector.extract_list(html, ".bookbox", "https://example.com", True)
    assert len(items) == 2

    first_name = RuleSelector.extract(items[0], "a.1@text", "https://example.com", True)
    first_url = RuleSelector.extract(items[0], "a.1@href", "https://example.com", True)
    first_author = RuleSelector.extract(items[0], "class.author@text", "https://example.com", True)

    assert first_name.success is True
    assert first_name.value == "斗罗大陆"
    assert first_url.value == "https://example.com/book-1"
    assert first_author.value == "唐家三少"


def test_rule_selector_extracts_json_and_text_nodes():
    data = {"data": {"list": [{"title": "第一章"}, {"title": "第二章"}]}}
    result = RuleSelector.extract(data, "$.data.list[*].title", "", False)
    assert result.success is True
    assert result.value == ["第一章", "第二章"]

    html = '<div id="content"><p>第一段</p><p>第二段</p></div>'
    content = RuleSelector.extract(html, "id.content@textNodes", "https://example.com", True)
    assert content.success is True
    assert content.value == ["第一段", "第二段"]


def test_rule_selector_supports_css_prefix():
    html = '<div class="result"><a href="/book-1">斗罗大陆</a></div>'
    item = RuleSelector.extract_list(html, "@css:.result", "https://example.com", True)[0]
    result = RuleSelector.extract(item, "@css:a@href", "https://example.com", True)
    assert result.success is True
    assert result.value == "https://example.com/book-1"


def test_rule_selector_regex_without_replacement_removes_matches():
    html = '<div class="con"><div>正文一</div><p>正文二</p></div>'
    result = RuleSelector.extract(html, "class.con@html##<div.*?>|</div>", "", True)
    assert result.success is True
    assert result.value == "正文一<p>正文二</p>"


def test_js_runtime_supports_mutable_result_and_memory_cache():
    runtime = JsRuntime()
    value = runtime.execute(
        """
result = JSON.parse(result);
cache.putMemory('articleid', result.data.articleid);
return result.data;
""",
        '{"data":{"articleid":362918,"name":"斗罗大陆"}}',
    )

    assert value["articleid"] == 362918
    assert runtime._cache["articleid"] == 362918


def test_js_runtime_returns_iife_expression_result():
    runtime = JsRuntime()
    value = runtime.execute(
        """
(function(result){
    result = JSON.parse(result);
    cache.putMemory('articleid', result.data.articleid);
    return result.data;
})(result);
""",
        '{"data":{"articleid":362918,"name":"斗罗大陆"}}',
    )

    assert value["articleid"] == 362918
    assert runtime._cache["articleid"] == 362918


def test_rule_selector_inline_js_passes_stage_context_into_runtime():
    class FakeRuntime:
        def __init__(self):
            self.received = None

        def execute(self, code, data=None, **kwargs):
            self.received = kwargs
            return "斗罗大陆"

    runtime = FakeRuntime()
    result = RuleSelector.extract(
        {"book": {"name": "ignored"}},
        "$.book@js: result.name",
        "https://novel.cooks.tw",
        False,
        context={"js_runtime": runtime, "stage": "search_rule_js"},
    )

    assert result.success is True
    assert result.value == "斗罗大陆"
    assert runtime.received["stage"] == "search_rule_js"



def test_rule_selector_extracts_direct_dict_key_name():
    result = RuleSelector.extract(
        {"KEYNAME": "斗罗大陆", "AUTHORNAME": "唐家三少"},
        "KEYNAME",
        "",
        False,
    )

    assert result.success is True
    assert result.value == "斗罗大陆"
