import pytest
from app.application.services.source_build_tool_executor import (
    SourceBuildToolContext,
    SourceBuildToolExecutor,
)
from app.services.generator import SourceGenerator


def test_source_build_tool_executor_rule_infer_tool():
    html = """
    <html>
      <head><title>笔趣阁小说网</title></head>
      <body>
        <form action="/search" method="get">
          <input type="text" name="keyword" />
        </form>
        <div id="list">
          <dl>
            <dd><a href="/1.html">第1章 觉醒</a></dd>
            <dd><a href="/2.html">第2章 进化</a></dd>
            <dd><a href="/3.html">第3章 终局</a></dd>
          </dl>
        </div>
      </body>
    </html>
    """
    context = SourceBuildToolContext(
        source_version_id="ver-1",
        source_url="https://www.biquge.com",
        source_rule={},
        inspect_data={"html_sample": html},
    )
    executor = SourceBuildToolExecutor(context)
    handlers = executor.handlers()

    assert "rule.infer" in handlers

    result = handlers["rule.infer"]({"html": html})
    assert result.status == "accepted"
    inferred = result.data["inferred_source"]
    assert inferred["bookSourceUrl"] == "https://www.biquge.com"
    assert inferred["ruleToc"]["chapterList"] != ""
    assert "keyword" in inferred["searchUrl"]


@pytest.mark.asyncio
async def test_generator_service_uses_induction_engine():
    generator = SourceGenerator()
    html = """
    <html>
      <head><title>修真聊天群最新章节 - 顶点小说</title></head>
      <body>
        <div id="catalog">
          <ul>
            <li><a href="/c1.html">第1章 我是书山压力大</a></li>
            <li><a href="/c2.html">第2章 奇怪的聊天群</a></li>
            <li><a href="/c3.html">第3章 各种丹药</a></li>
          </ul>
        </div>
      </body>
    </html>
    """
    source = await generator._generate_book_source("https://www.dingdian.org", html, "顶点小说")
    assert source is not None
    assert source["ruleToc"]["chapterList"] != ""
    assert "a" in source["ruleToc"]["chapterList"] or "catalog" in source["ruleToc"]["chapterList"]
