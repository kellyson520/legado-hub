import pytest
from bs4 import BeautifulSoup
from app.application.services.source_induction_service import SourceInductionService


def test_infer_toc_rule_identifies_chapter_links_and_container():
    html = """
    <html>
      <body>
        <div class="header"><a href="/">首页</a><a href="/rank">排行榜</a></div>
        <div id="list">
          <dl>
            <dt>正文章节</dt>
            <dd><a href="/book/101/1.html">第1章 惊变</a></dd>
            <dd><a href="/book/101/2.html">第2章 逃亡</a></dd>
            <dd><a href="/book/101/3.html">第3章 绝地反击</a></dd>
            <dd><a href="/book/101/4.html">第4章 神秘来客</a></dd>
            <dd><a href="/book/101/5.html">第5章 启程</a></dd>
          </dl>
        </div>
        <div class="footer"><a href="/about">关于我们</a></div>
      </body>
    </html>
    """
    service = SourceInductionService()
    toc_rule = service.infer_toc_rule(BeautifulSoup(html, "lxml"))

    assert toc_rule["chapterList"] != ""
    # Should identify elements under #list or dl dd a
    assert "dd a" in toc_rule["chapterList"] or "#list" in toc_rule["chapterList"]
    assert toc_rule["chapterName"] in ("text", "a@text")
    assert "href" in toc_rule["chapterUrl"]


def test_infer_content_rule_detects_dense_text_block_and_filters_noise():
    html = """
    <html>
      <body>
        <div class="nav"><p>顶部导航</p></div>
        <div class="ad-banner">广告内容广告内容广告内容</div>
        <div id="chaptercontent">
          <p>夜幕降临，林默站在城头，望着远方的滚滚烽烟。</p>
          <p>“这一战，我们退无可退。”身后传来了低沉而坚定的声音。</p>
          <p>他握紧手中的刀柄，指节因用力而发白。城墙下，黑压压的军队如潮水般涌动，杀气直冲霄汉。</p>
          <p>“那就死战到底！”</p>
        </div>
        <div class="comment-box"><p>读者评论：太精彩了！</p></div>
      </body>
    </html>
    """
    service = SourceInductionService()
    content_rule = service.infer_content_rule(BeautifulSoup(html, "lxml"))

    assert "#chaptercontent" in content_rule["content"] or "chaptercontent" in content_rule["content"]


def test_infer_search_rule_detects_form_method_and_query_param():
    html = """
    <html>
      <body>
        <form action="/modules/article/search.php" method="post">
          <input type="text" name="searchkey" placeholder="请输入小说名" />
          <input type="submit" value="搜索" />
        </form>
      </body>
    </html>
    """
    service = SourceInductionService()
    search_rule = service.infer_search_rule(BeautifulSoup(html, "lxml"), base_url="https://www.readnovel.com")

    assert search_rule["searchUrl"] != ""
    assert "searchkey" in search_rule["searchUrl"]
    assert "https://www.readnovel.com/modules/article/search.php" in search_rule["searchUrl"]


def test_infer_full_source_generates_legado_schema():
    toc_html = """
    <html>
      <head><title>全职高手最新章节 - 顶点小说</title></head>
      <body>
        <div class="catalog">
          <ul class="chapters">
            <li><a href="/ch/1.html">第1章 被驱逐的高手</a></li>
            <li><a href="/ch/2.html">第2章 C区47号</a></li>
            <li><a href="/ch/3.html">第3章 专职千机伞</a></li>
            <li><a href="/ch/4.html">第4章 荣耀，再见</a></li>
            <li><a href="/ch/5.html">第5章 蜘蛛洞穴</a></li>
          </ul>
        </div>
      </body>
    </html>
    """
    content_html = """
    <html>
      <body>
        <div id="content">
          “如果喜欢，就把这一切当作是荣耀，而不是炫耀。”
          全职高手的传奇在这里翻开新篇章。
        </div>
      </body>
    </html>
    """
    service = SourceInductionService()
    source = service.infer_source_from_html(
        base_url="https://www.dingdian.com",
        toc_html=toc_html,
        content_html=content_html,
    )

    assert source["bookSourceUrl"] == "https://www.dingdian.com"
    assert "全职高手" in source["bookSourceName"] or "顶点小说" in source["bookSourceName"]
    assert source["ruleToc"]["chapterList"] != ""
    assert source["ruleContent"]["content"] != ""
