from app.application.services.source_induction_service import SourceInductionService


def test_source_builder_agent_generates_valid_source():
    induction = SourceInductionService()

    # Synthetic realistic novel HTML
    toc_html = """
    <html>
      <head><title>修真世界 - 最新章节列表</title></head>
      <body>
        <div class="header"><h1>修真世界</h1></div>
        <form action="/search" method="get">
          <input type="text" name="keyword" />
          <button type="submit">搜索</button>
        </form>
        <div class="chapter-box">
          <ul class="chapter-list">
            <li><a href="/chapter/1.html">第一章 仙石</a></li>
            <li><a href="/chapter/2.html">第二章 筑基</a></li>
            <li><a href="/chapter/3.html">第三章 突破</a></li>
          </ul>
        </div>
      </body>
    </html>
    """
    content_html = """
    <html>
      <body>
        <div class="content" id="chapter-content">
          <p>天道无情，大道三千...</p>
          <p>林轩盘膝而坐，体内真气翻涌。</p>
        </div>
      </body>
    </html>
    """

    source = induction.infer_source_from_html(
        base_url="https://www.xiuzhen-test.com",
        toc_html=toc_html,
        content_html=content_html,
        source_name="修真世界测试源",
    )

    assert source["bookSourceName"] == "修真世界测试源"
    assert source["bookSourceUrl"] == "https://www.xiuzhen-test.com"
    assert "chapterList" in source["ruleToc"]
    assert source["ruleToc"]["chapterList"] != ""
    assert "content" in source["ruleContent"]
    assert source["ruleContent"]["content"] != ""
