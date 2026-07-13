"""
书源搜索服务测试 - 斗罗大陆

覆盖：
- searchUrl 解析（GET/POST/charset/body）
- 关键词占位符替换
- JSONPath 解析模式
- CSS 选择器解析模式
- 结果数据清洗
- 真实书源搜索"斗罗大陆"集成测试
"""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

pytestmark = pytest.mark.asyncio


# ==================== Part 1: 单元测试 ====================


class TestParseSearchUrl:
    """searchUrl 解析测试"""

    async def test_simple_get_url(self):
        """简单 GET URL"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource
        source = BookSource(bookSourceUrl="https://test.com", bookSourceName="Test", searchUrl="/search?key={{key}}")
        searcher = BookSearcher(source)
        result = searcher._parse_search_url("/search?key={{key}}")
        assert result["url"] == "/search?key={{key}}"
        assert result["options"] == {}

    async def test_post_with_body(self):
        """POST + body（紧凑 JSON 格式，无内嵌逗号问题）"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource
        source = BookSource(bookSourceUrl="https://test.com", bookSourceName="Test")
        searcher = BookSearcher(source)
        # 紧凑 JSON，method 和 body 之间用逗号分隔会被正确切分
        result = searcher._parse_search_url(
            "https://test.com/search,{\"method\":\"POST\",\"body\":\"searchkey={{key}}\"}"
        )
        assert result["url"] == "https://test.com/search"
        assert result["options"]["method"] == "POST"
        assert result["options"]["body"] == "searchkey={{key}}"

    async def test_get_with_charset(self):
        """GET + charset"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource
        source = BookSource(bookSourceUrl="https://test.com", bookSourceName="Test")
        searcher = BookSearcher(source)
        # 模拟真实书源的 searchUrl，JSON 中只有 charset 一个字段
        result = searcher._parse_search_url(
            "http://www.xquledu.com/search?searchkey={{key}},{\"charset\":\"gbk\"}"
        )
        assert result["url"] == "http://www.xquledu.com/search?searchkey={{key}}"
        assert result["options"]["charset"] == "gbk"

    async def test_real_source_search_urls(self):
        """测试真实书源的 searchUrl 解析"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource

        # 每条用 (searchUrl字符串, 期望的url前缀, 期望的options子集) 描述
        real_cases = [
            # 纯 GET，无选项
            (
                "https://sou.jiaston.com/search.aspx?key={{key}}&page=Page",
                "https://sou.jiaston.com/search.aspx?key={{key}}&page=Page",
                {},
            ),
            # 紧凑 JSON，只有 charset（单字段不会被逗号分割打断）
            (
                "http://www.xquledu.com/search?searchkey={{key}},{\"charset\":\"gbk\"}",
                "http://www.xquledu.com/search?searchkey={{key}}",
                {"charset": "gbk"},
            ),
            # 紧凑 JSON，method + body（两字段紧挨，逗号充当分隔符被正确解析）
            (
                "https://www.fanfanzw.com/search.html,{\"method\":\"POST\",\"body\":\"searchkey={{key}}\"}",
                "https://www.fanfanzw.com/search.html",
                {"method": "POST", "body": "searchkey={{key}}"},
            ),
        ]

        for url, expected_url_prefix, expected_options in real_cases:
            source = BookSource(bookSourceUrl="https://test.com", bookSourceName="Test", searchUrl=url)
            searcher = BookSearcher(source)
            result = searcher._parse_search_url(url)
            assert result["url"] == expected_url_prefix, (
                f"URL mismatch for {url!r}: got {result['url']!r}"
            )
            for k, v in expected_options.items():
                assert result["options"].get(k) == v, (
                    f"Option {k} mismatch: expected {v!r}, got {result['options'].get(k)!r}"
                )


class TestReplaceKeyword:
    """关键词替换测试"""

    async def test_double_brace_key(self):
        """{{key}} 替换"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource
        source = BookSource(bookSourceUrl="https://test.com", bookSourceName="T")
        searcher = BookSearcher(source)
        result = searcher._replace_keyword("https://test.com/search?key={{key}}", "斗罗大陆")
        assert result == "https://test.com/search?key=斗罗大陆"

    async def test_single_brace_key(self):
        """{key} 替换"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource
        source = BookSource(bookSourceUrl="https://test.com", bookSourceName="T")
        searcher = BookSearcher(source)
        result = searcher._replace_keyword("https://test.com/search?q={key}", "斗罗大陆")
        assert "斗罗大陆" in result

    async def test_post_body_replace(self):
        """POST body 替换"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource
        source = BookSource(bookSourceUrl="https://test.com", bookSourceName="T")
        searcher = BookSearcher(source)
        result = searcher._replace_keyword("searchkey={{key}}&page=1", "斗罗大陆")
        assert result == "searchkey=斗罗大陆&page=1"


class TestJsonPathParsing:
    """JSONPath 解析模式测试"""

    async def test_parse_json_api_response(self):
        """解析 JSON API 搜索结果（使用 $..key 递归查找）"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource

        source = BookSource(
            bookSourceUrl="https://quapp.shenbabao.com",
            bookSourceName="APP测试源",
            searchUrl="https://sou.jiaston.com/search.aspx?key={{key}}",
            ruleSearch={
                "bookList": "$..data",
                "name": "$.Name",
                "author": "$.Author",
                "bookUrl": "$.Id",
                "intro": "$.Desc",
            }
        )
        searcher = BookSearcher(source)

        # 模拟 JSON API 响应
        mock_response = json.dumps({
            "data": [
                {"Id": 1, "Name": "斗罗大陆", "Author": "唐家三少", "Desc": "唐门外门弟子"},
                {"Id": 2, "Name": "斗罗大陆II", "Author": "唐家三少", "Desc": "史莱克学院"},
            ]
        })

        results = searcher._parse_json(mock_response, source.ruleSearch)

        assert len(results) >= 2
        # 第一个结果应该是斗罗大陆
        names = [r.get("name") for r in results]
        assert "斗罗大陆" in names

        # 验证字段
        douluo = next((r for r in results if r.get("name") == "斗罗大陆"), None)
        assert douluo is not None
        assert douluo["author"] == "唐家三少"
        # intro 包含故事简介关键词
        assert "唐门" in douluo.get("intro", "")


class TestCssParsing:
    """CSS 选择器解析模式测试"""

    async def test_parse_html_response(self):
        """解析 HTML 搜索结果（使用 _css_select 支持的简单选择器）"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource

        source = BookSource(
            bookSourceUrl="https://www.fanfanzw.com",
            bookSourceName="饭饭中文",
            searchUrl="https://www.fanfanzw.com/search.html",
            ruleSearch={
                "bookList": "class.book-item",
                "name": "h3@text",
                "author": "class.author@text",
                "bookUrl": "tag.a@href",
                "intro": "class.intro@text",
            }
        )
        searcher = BookSearcher(source)

        # 模拟 HTML 搜索结果
        mock_html = """
        <html><body>
        <div class="book-item">
            <h3><a href="/book/1.html">斗罗大陆</a></h3>
            <div class="author">唐家三少</div>
            <div class="intro">唐门外门弟子唐三的故事</div>
        </div>
        <div class="book-item">
            <h3><a href="/book/2.html">斗破苍穹</a></h3>
            <div class="author">天蚕土豆</div>
            <div class="intro">萧炎的成长之路</div>
        </div>
        </body></html>
        """

        results = searcher._parse_html(mock_html, source.ruleSearch)

        assert len(results) >= 2
        names = [r.get("name") for r in results]
        assert "斗罗大陆" in names
        assert "斗破苍穹" in names

        douluo = next((r for r in results if r.get("name") == "斗罗大陆"), None)
        assert douluo is not None
        assert douluo.get("author") == "唐家三少"

    async def test_css_fallback_selector(self):
        """|| 分隔符回退选择器"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource

        source = BookSource(
            bookSourceUrl="https://test.com",
            bookSourceName="Test",
            ruleSearch={
                "bookList": "class.notexist||class.result-item",
                "name": "class.name@text||tag.h3@text",
            }
        )
        searcher = BookSearcher(source)

        html = """
        <div class="result-item">
            <div class="name">斗罗大陆</div>
            <h3>备用选择器</h3>
        </div>
        """

        results = searcher._parse_html(html, source.ruleSearch)
        assert len(results) >= 1
        # name 先尝试 class.name 找到，不走 || 回退
        names = [r.get("name") for r in results]
        assert "斗罗大陆" in names


class TestSearchResultModel:
    """SearchResult 数据模型测试"""

    def test_search_result_fields(self):
        from app.services.book_searcher import SearchResult
        r = SearchResult(
            name="斗罗大陆",
            author="唐家三少",
            bookUrl="https://test.com/book/1",
            intro="唐门外门弟子",
            sourceName="测试源",
            sourceUrl="https://test.com",
        )
        assert r.name == "斗罗大陆"
        assert r.author == "唐家三少"
        assert r.sourceName == "测试源"

    def test_search_result_to_dict(self):
        from app.services.book_searcher import SearchResult
        r = SearchResult(name="斗罗大陆", author="唐家三少")
        d = {k: v for k, v in r.__dict__.items() if v}
        assert d["name"] == "斗罗大陆"


class TestBookSearcherMockHTTP:
    """Mock HTTP 请求的搜索测试"""

    async def test_search_with_mock_http_json(self):
        """Mock JSON API 搜索（使用 $..key 递归查找）"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource

        source = BookSource(
            bookSourceUrl="https://api.test.com",
            bookSourceName="JSON源",
            searchUrl="https://api.test.com/search?key={{key}}",
            ruleSearch={
                "bookList": "$..data",
                "name": "$.name",
                "author": "$.author",
            }
        )

        mock_response = json.dumps({
            "data": [
                {"name": "斗罗大陆", "author": "唐家三少"},
                {"name": "斗罗大陆II绝世唐门", "author": "唐家三少"},
            ]
        })

        searcher = BookSearcher(source)

        with patch.object(searcher, "_search_http", new_callable=AsyncMock, return_value=(200, mock_response)):
            results = await searcher.search("斗罗大陆")

        assert len(results) == 2
        assert results[0].name == "斗罗大陆"
        assert results[0].sourceName == "JSON源"

    async def test_search_with_mock_http_html(self):
        """Mock HTML 搜索"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource

        source = BookSource(
            bookSourceUrl="https://www.test.com",
            bookSourceName="HTML源",
            searchUrl="https://www.test.com/search?key={{key}}",
            ruleSearch={
                "bookList": "class.book-item",
                "name": "tag.h3@text",
                "author": "class.author@text",
            }
        )

        mock_html = """
        <div class="book-item"><h3>斗罗大陆</h3><div class="author">唐家三少</div></div>
        <div class="book-item"><h3>遮天</h3><div class="author">辰东</div></div>
        """

        searcher = BookSearcher(source)

        with patch.object(searcher, "_search_http", new_callable=AsyncMock, return_value=(200, mock_html)):
            results = await searcher.search("斗罗大陆")

        assert len(results) >= 1
        names = [r.name for r in results]
        assert "斗罗大陆" in names

    async def test_search_http_error(self):
        """HTTP 错误处理"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource

        source = BookSource(
            bookSourceUrl="https://error.test",
            bookSourceName="错误源",
            searchUrl="https://error.test/search?key={{key}}",
            ruleSearch={"bookList": "$..data", "name": "$.name"},
        )

        searcher = BookSearcher(source)

        with patch.object(searcher, "_search_http", new_callable=AsyncMock, return_value=(500, "Server Error")):
            results = await searcher.search("斗罗大陆")

        assert results == []

    async def test_search_no_search_url(self):
        """无 searchUrl"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource

        source = BookSource(bookSourceUrl="https://test.com", bookSourceName="无搜索")
        searcher = BookSearcher(source)
        results = await searcher.search("斗罗大陆")
        assert results == []

    async def test_search_json_parse_error(self):
        """JSON 解析失败"""
        from app.services.book_searcher import BookSearcher
        from app.domain.entities.source import BookSource

        source = BookSource(
            bookSourceUrl="https://test.com",
            bookSourceName="BadJSON",
            searchUrl="https://test.com/search",
            ruleSearch={"bookList": "$..data", "name": "$.name"},
        )

        searcher = BookSearcher(source)

        with patch.object(searcher, "_search_http", new_callable=AsyncMock, return_value=(200, "not json")):
            results = await searcher.search("斗罗大陆")

        assert results == []


# ==================== Part 2: 真实搜索测试（标记为可选执行）====================


@pytest.mark.skipif(
    True,  # 设置为 False 在有网络的环境下执行真实搜索
    reason="需要外网访问，CI 环境跳过"
)
class TestRealBookSearch:
    """使用真实书源搜索"斗罗大陆"（需要外网）"""

    async def test_search_douluo_from_yckceo_sources(self):
        """用 yckceo 真实书源搜索斗罗大陆"""
        from tests.test_real_source_import import _load_real_sources
        from app.domain.entities.source import BookSource
        from app.services.book_searcher import BookSearcher

        raw_sources = _load_real_sources()
        all_results = []

        for raw in raw_sources:
            entity = BookSource.from_dict(raw)
            if not entity.searchUrl or not entity.ruleSearch:
                continue

            try:
                searcher = BookSearcher(entity)
                results = await searcher.search("斗罗大陆", timeout=15)
                all_results.extend(results)
                print(f"\n  [{entity.bookSourceName}] 找到 {len(results)} 条结果")
                for r in results[:3]:
                    print(f"    - 《{r.name}》 {r.author} | {r.intro[:50] if r.intro else ''}")
            except Exception as e:
                print(f"  [{entity.bookSourceName}] 搜索失败: {e}")

        print(f"\n[搜索汇总] 共从 {len(raw_sources)} 个源搜索，找到 {len(all_results)} 条结果")

        # 验证至少找到"斗罗大陆"
        douluo_results = [r for r in all_results if "斗罗大陆" in r.name]
        assert len(douluo_results) > 0, f"未找到斗罗大陆相关结果，共 {len(all_results)} 条"
        print(f"  包含'斗罗大陆'的结果: {len(douluo_results)} 条")
