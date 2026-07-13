"""
爬虫引擎单元测试

测试 Crawler 基础设施层的核心功能：
- CrawlResult 数据结构
- CrawlerEngine 单例模式
- UA 轮换
- CSS/XPath/正则解析
- 错误处理
"""

import pytest
from unittest.mock import patch, MagicMock


# ==================== CrawlResult 测试 ====================

class TestCrawlResult:
    def test_result_defaults(self):
        from app.infrastructure.crawler import CrawlResult
        result = CrawlResult(url="https://example.com")
        assert result.url == "https://example.com"
        assert result.success is True
        assert result.status_code == 200
        assert result.html == ""
        assert result.json_data is None
        assert result.error is None
        assert result.elapsed_ms == 0.0

    def test_text_alias(self):
        from app.infrastructure.crawler import CrawlResult
        result = CrawlResult(url="https://example.com", html="<p>hello</p>")
        assert result.text == result.html

    def test_regex_extraction(self):
        from app.infrastructure.crawler import CrawlResult
        html = '<div class="title">第一百二十三章 测试章节</div>'
        result = CrawlResult(url="https://example.com", html=html)
        matches = result.regex(r'class="title">([^<]+)<')
        assert len(matches) > 0
        assert "第一百二十三章" in matches[0]

    def test_regex_invalid_pattern(self):
        from app.infrastructure.crawler import CrawlResult
        result = CrawlResult(url="https://example.com", html="test")
        matches = result.regex(r"[invalid")  # 无效正则
        assert matches == []

    def test_css_select(self):
        from app.infrastructure.crawler import CrawlResult
        html = """
        <html><body>
            <h1>标题</h1>
            <div class="chapter">第一章</div>
            <div class="chapter">第二章</div>
        </body></html>
        """
        result = CrawlResult(url="https://example.com", html=html)
        chapters = result.css_select("div.chapter")
        assert len(chapters) == 2
        assert "第一章" in chapters

    def test_css_select_first(self):
        from app.infrastructure.crawler import CrawlResult
        html = """
        <html><body>
            <p class="first">第一个</p>
            <p class="second">第二个</p>
        </body></html>
        """
        result = CrawlResult(url="https://example.com", html=html)
        first = result.css_select_first("p.first")
        assert first == "第一个"

    def test_css_select_empty(self):
        from app.infrastructure.crawler import CrawlResult
        result = CrawlResult(url="https://example.com", html="<html></html>")
        results = result.css_select(".nonexistent")
        assert results == []

    def test_xpath_extraction(self):
        from app.infrastructure.crawler import CrawlResult
        html = """
        <html><body>
            <ul id="list">
                <li>第一项</li>
                <li>第二项</li>
            </ul>
        </body></html>
        """
        result = CrawlResult(url="https://example.com", html=html)
        items = result.xpath('//ul[@id="list"]/li/text()')
        assert len(items) == 2


# ==================== CrawlerEngine 测试 ====================

class TestCrawlerEngine:
    def test_singleton(self):
        """单例模式测试"""
        from app.infrastructure.crawler import CrawlerEngine
        engine1 = CrawlerEngine()
        engine2 = CrawlerEngine()
        assert engine1 is engine2

    def test_user_agents_loaded(self):
        """UA 列表应该加载"""
        from app.infrastructure.crawler import USER_AGENTS
        assert len(USER_AGENTS) > 0
        assert all("Mozilla" in ua for ua in USER_AGENTS)

    def test_random_ua_in_list(self):
        """随机 UA 应该在列表中"""
        from app.infrastructure.crawler import CrawlerEngine, USER_AGENTS
        engine = CrawlerEngine()
        ua = engine._random_ua()
        assert ua in USER_AGENTS

    def test_get_request_mock(self):
        """GET 请求 mock 测试"""
        from app.infrastructure.crawler import CrawlerEngine

        engine = CrawlerEngine()

        # Mock requests.Session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>Hello</html>"
        mock_response.encoding = "utf-8"
        mock_response.apparent_encoding = "utf-8"
        mock_response.url = "https://example.com"
        mock_response.headers = {"content-type": "text/html"}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch.object(engine, '_get_session', return_value=mock_session):
            with patch.object(engine, '_rate_limit'):
                result = engine.get("https://example.com")

        assert result.success is True
        assert result.status_code == 200
        assert "Hello" in result.html

    def test_get_failure_retry(self):
        """失败重试测试"""
        from app.infrastructure.crawler import CrawlerEngine

        engine = CrawlerEngine(max_retries=3, retry_delay=0)

        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Connection error")

        with patch.object(engine, '_get_session', return_value=mock_session):
            with patch.object(engine, '_rate_limit'):
                result = engine.get("https://example.com")

        assert result.success is False
        assert result.error is not None
        # 应该调用了 3 次
        assert mock_session.get.call_count == 3

    def test_post_request_mock(self):
        """POST 请求 mock 测试"""
        from app.infrastructure.crawler import CrawlerEngine

        engine = CrawlerEngine()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "ok"}'
        mock_response.encoding = "utf-8"
        mock_response.apparent_encoding = "utf-8"
        mock_response.url = "https://example.com/api"
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"status": "ok"}

        mock_session = MagicMock()
        mock_session.post.return_value = mock_response

        with patch.object(engine, '_get_session', return_value=mock_session):
            with patch.object(engine, '_rate_limit'):
                result = engine.post("https://example.com/api", json={"query": "test"})

        assert result.success is True
        assert result.json_data == {"status": "ok"}

    def test_batch_get(self):
        """批量 GET 测试"""
        from app.infrastructure.crawler import CrawlerEngine

        engine = CrawlerEngine()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"
        mock_response.encoding = "utf-8"
        mock_response.apparent_encoding = "utf-8"
        mock_response.url = "https://example.com"
        mock_response.headers = {}

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch.object(engine, '_get_session', return_value=mock_session):
            with patch.object(engine, '_rate_limit'):
                results = engine.batch_get([
                    "https://example.com/1",
                    "https://example.com/2",
                    "https://example.com/3",
                ])

        assert len(results) == 3
        assert all(r.success for r in results)
