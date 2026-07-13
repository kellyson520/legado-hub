import shutil

import pytest

from app.infrastructure.legado.engine.js_runtime import JsRuntime


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required for jsoup tests")


def test_jsoup_parse_select_text_html_and_attr():
    runtime = JsRuntime()
    output = runtime.execute_with_metadata(
        """
        var doc = org.jsoup.Jsoup.parse(result);
        return {
          title: doc.select('.title').text(),
          href: doc.select('a.title').attr('href'),
          html: doc.select('#intro').html()
        };
        """,
        data='<div><a class="title" href="/book-1">斗罗大陆</a><div id="intro"><p>第一部</p></div></div>',
        stage="content_rule_js",
        source={"bookSourceName": "jsoup-test", "bookSourceUrl": "https://a.example.com"},
        baseUrl="https://a.example.com",
    )

    assert output.success is True
    assert output.value["title"] == "斗罗大陆"
    assert output.value["href"] == "/book-1"
    assert "第一部" in output.value["html"]
