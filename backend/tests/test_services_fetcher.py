"""
测试 SourceFetcher 的纯逻辑方法: parse_sources_from_text

测试范围:
- JSON 数组格式解析（单个书源、单个订阅源、混合列表）
- NDJSON（每行一个 JSON）格式解析
- 空内容处理
- 非法 JSON 行容错（NDJSON 模式下跳过错误行）
- 源分类逻辑: bookSourceUrl 归入书源，sourceUrl 归入订阅源
- sourceOrigin 标注
- 不涉及网络操作，不测试 fetch_url / fetch_subscription
"""

import pytest
import json
from app.services.fetcher import SourceFetcher


@pytest.fixture
def fetcher():
    """创建 SourceFetcher 实例（纯逻辑测试，无需异步上下文管理器）"""
    return SourceFetcher()


class TestParseSourcesFromTextJsonArray:
    """测试标准 JSON 数组格式的书源解析"""

    def test_空文本返回空列表(self, fetcher):
        # 空字符串
        book_sources, rss_sources = fetcher.parse_sources_from_text("")
        assert book_sources == []
        assert rss_sources == []

    def test_纯空白文本返回空列表(self, fetcher):
        # 只有空白字符
        book_sources, rss_sources = fetcher.parse_sources_from_text("   \n\t  ")
        assert book_sources == []
        assert rss_sources == []

    def test_单个书源解析(self, fetcher):
        # JSON 数组中只有一个书源
        text = json.dumps([{
            "bookSourceUrl": "https://book.example.com",
            "bookSourceName": "示例书源",
            "bookSourceGroup": "测试",
        }])
        book_sources, rss_sources = fetcher.parse_sources_from_text(text)
        assert len(book_sources) == 1
        assert len(rss_sources) == 0
        assert book_sources[0]["bookSourceUrl"] == "https://book.example.com"
        assert book_sources[0]["bookSourceName"] == "示例书源"

    def test_单个订阅源解析(self, fetcher):
        # JSON 数组中只有一个订阅源
        text = json.dumps([{
            "sourceUrl": "https://rss.example.com",
            "sourceName": "示例RSS",
        }])
        book_sources, rss_sources = fetcher.parse_sources_from_text(text)
        assert len(book_sources) == 0
        assert len(rss_sources) == 1
        assert rss_sources[0]["sourceUrl"] == "https://rss.example.com"

    def test_混合书源和订阅源(self, fetcher):
        # JSON 数组中同时包含书源和订阅源
        text = json.dumps([
            {"bookSourceUrl": "https://book1.com", "bookSourceName": "书源1"},
            {"sourceUrl": "https://rss1.com", "sourceName": "RSS1"},
            {"bookSourceUrl": "https://book2.com", "bookSourceName": "书源2"},
            {"sourceUrl": "https://rss2.com", "sourceName": "RSS2"},
        ])
        book_sources, rss_sources = fetcher.parse_sources_from_text(text, origin="https://sub.url")
        assert len(book_sources) == 2
        assert len(rss_sources) == 2
        # 验证 sourceOrigin 被正确设置
        assert book_sources[0]["sourceOrigin"] == "https://sub.url"
        assert rss_sources[0]["sourceOrigin"] == "https://sub.url"

    def test_json对象而非数组也支持(self, fetcher):
        # 单个 JSON 对象（非数组）
        text = json.dumps({
            "bookSourceUrl": "https://single.com",
            "bookSourceName": "单个书源",
        })
        book_sources, rss_sources = fetcher.parse_sources_from_text(text)
        assert len(book_sources) == 1
        assert book_sources[0]["bookSourceUrl"] == "https://single.com"

    def test_searchUrl字段归入订阅源(self, fetcher):
        # 有 searchUrl 但无 bookSourceName 的应归入订阅源
        text = json.dumps([{
            "searchUrl": "https://search.example.com/search",
            "sourceName": "搜索源",
        }])
        book_sources, rss_sources = fetcher.parse_sources_from_text(text)
        assert len(book_sources) == 0
        assert len(rss_sources) == 1
        assert rss_sources[0]["searchUrl"] == "https://search.example.com/search"

    def test_非字典元素被忽略(self, fetcher):
        # JSON 数组中包含非字典元素（如字符串、数字）
        text = json.dumps(["不是源", 123, None, {"bookSourceUrl": "https://valid.com", "bookSourceName": "有效"}])
        book_sources, rss_sources = fetcher.parse_sources_from_text(text)
        # 只有有效的字典元素被解析
        assert len(book_sources) == 1
        # 非字典元素不会导致崩溃


class TestParseSourcesFromTextNdjson:
    """测试 NDJSON（每行一个 JSON）格式的解析"""

    def test_ndjson基本解析(self, fetcher):
        # 多行 NDJSON 格式
        lines = [
            json.dumps({"bookSourceUrl": "https://a.com", "bookSourceName": "书源A"}),
            json.dumps({"sourceUrl": "https://b.com", "sourceName": "RSS_B"}),
            json.dumps({"bookSourceUrl": "https://c.com", "bookSourceName": "书源C"}),
        ]
        text = "\n".join(lines)
        book_sources, rss_sources = fetcher.parse_sources_from_text(text)
        assert len(book_sources) == 2
        assert len(rss_sources) == 1

    def test_ndjson跳过空行(self, fetcher):
        # NDJSON 中有空行
        lines = [
            json.dumps({"bookSourceUrl": "https://a.com", "bookSourceName": "A"}),
            "",
            "   ",
            json.dumps({"bookSourceUrl": "https://b.com", "bookSourceName": "B"}),
        ]
        text = "\n".join(lines)
        book_sources, rss_sources = fetcher.parse_sources_from_text(text)
        assert len(book_sources) == 2

    def test_ndjson非法行被跳过(self, fetcher):
        # NDJSON 中有非法 JSON 行，应被跳过而不崩溃
        lines = [
            json.dumps({"bookSourceUrl": "https://valid.com", "bookSourceName": "有效"}),
            "{非法json内容",
            "not json at all",
            json.dumps({"sourceUrl": "https://rss.com", "sourceName": "RSS"}),
        ]
        text = "\n".join(lines)
        book_sources, rss_sources = fetcher.parse_sources_from_text(text)
        # 有效行被解析，非法行被跳过
        assert len(book_sources) == 1
        assert len(rss_sources) == 1

    def test_ndjson全部非法行(self, fetcher):
        # 所有行都是非法 JSON
        text = "not json\n{broken\nalso not json"
        book_sources, rss_sources = fetcher.parse_sources_from_text(text)
        assert book_sources == []
        assert rss_sources == []

    def test_ndjson_origin参数传递(self, fetcher):
        # NDJSON 格式验证 origin 参数
        text = json.dumps({"bookSourceUrl": "https://x.com", "bookSourceName": "X"}) + "\n" + \
               json.dumps({"sourceUrl": "https://y.com", "sourceName": "Y"})
        book_sources, rss_sources = fetcher.parse_sources_from_text(text, origin="https://origin.url")
        assert book_sources[0]["sourceOrigin"] == "https://origin.url"
        assert rss_sources[0]["sourceOrigin"] == "https://origin.url"


class TestParseSourcesFromTextEdgeCases:
    """边界条件和异常场景"""

    def test_既无bookSourceUrl也无sourceUrl的分类(self, fetcher):
        # 既没有 bookSourceUrl 也没有 sourceUrl 的字典
        text = json.dumps([{"name": "无法分类的源"}])
        book_sources, rss_sources = fetcher.parse_sources_from_text(text)
        # 无法分类的源不应归入任何列表
        assert len(book_sources) == 0
        assert len(rss_sources) == 0

    def test_bookSourceUrl优先于sourceUrl(self, fetcher):
        # 同时有 bookSourceUrl 和 sourceUrl 时，应归入书源
        text = json.dumps([{
            "bookSourceUrl": "https://book.com",
            "sourceUrl": "https://rss.com",
            "bookSourceName": "双重URL",
        }])
        book_sources, rss_sources = fetcher.parse_sources_from_text(text)
        assert len(book_sources) == 1
        assert len(rss_sources) == 0
        assert book_sources[0]["bookSourceUrl"] == "https://book.com"

    def test_大量书源解析性能(self, fetcher):
        # 验证大量数据不会崩溃
        sources = [{"bookSourceUrl": f"https://src{i}.com", "bookSourceName": f"源{i}"} for i in range(100)]
        text = json.dumps(sources)
        book_sources, rss_sources = fetcher.parse_sources_from_text(text)
        assert len(book_sources) == 100
        assert len(rss_sources) == 0

    def test_unicode内容正确处理(self, fetcher):
        # Unicode 字符（中文、emoji）正常解析
        text = json.dumps([{
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试书源",
        }])
        book_sources, _ = fetcher.parse_sources_from_text(text)
        assert book_sources[0]["bookSourceName"] == "测试书源"

    def test_返回的字典包含原始所有字段(self, fetcher):
        # 验证原始字段都被保留（除 sourceOrigin 被追加外）
        source = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试",
            "bookSourceGroup": "默认",
            "searchUrl": "https://example.com/search",
        }
        text = json.dumps([source])
        book_sources, _ = fetcher.parse_sources_from_text(text)
        result = book_sources[0]
        assert result["bookSourceUrl"] == source["bookSourceUrl"]
        assert result["bookSourceName"] == source["bookSourceName"]
        assert result["bookSourceGroup"] == source["bookSourceGroup"]
        assert result["searchUrl"] == source["searchUrl"]
        # sourceOrigin 被追加
        assert "sourceOrigin" in result
