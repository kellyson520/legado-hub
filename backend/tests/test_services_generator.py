"""
测试 SourceGenerator 的 generate 方法

测试范围:
- URL 校验（非法 URL 抛出 ValidationException）
- 网络拉取成功场景: RSS/Atom XML、HTML 页面
- 网络失败兜底: 连接超时、连接错误时使用 compat_engine 兜底
- 解析失败兜底: 页面结构无法识别时兜底
- 通过 mock aiohttp 隔离网络依赖
- _fetch_page 私有方法通过 generate 间接测试
- MemoryEventBus 的 publish/subscribe/on_event 便捷函数
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from app.services.generator import SourceGenerator
from app.core.exceptions import ValidationException
from app.core.events import (
    MemoryEventBus, DomainEvent, SourceFetchedEvent,
    publish_event, on_event
)


# ==================== SourceGenerator 测试 ====================

class TestSourceGeneratorUrlValidation:
    """测试 URL 校验逻辑"""

    @pytest.mark.asyncio
    async def test_空URL抛出ValidationException(self):
        generator = SourceGenerator()
        with pytest.raises(ValidationException, match="URL 必须以 http:// 或 https:// 开头"):
            await generator.generate("")

    @pytest.mark.asyncio
    async def test_非http协议抛出ValidationException(self):
        generator = SourceGenerator()
        with pytest.raises(ValidationException, match="URL 必须以 http:// 或 https:// 开头"):
            await generator.generate("ftp://example.com/feed.xml")

    @pytest.mark.asyncio
    async def test_无协议前缀抛出ValidationException(self):
        generator = SourceGenerator()
        with pytest.raises(ValidationException):
            await generator.generate("example.com/feed.xml")

    @pytest.mark.asyncio
    async def test_http和https协议正常通过(self):
        """验证 http/https 不会在校验阶段被拦截"""
        generator = SourceGenerator()

        # mock _fetch_page 避免实际网络请求
        generator._fetch_page = AsyncMock(return_value=("<html></html>", "text/html"))

        # mock 内部解析方法，避免 BeautifulSoup 依赖
        with patch.object(generator, '_generate_rss_source_from_html', new_callable=AsyncMock, return_value=None):
            with patch.object(generator, '_detect_article_list', return_value=None):
                # 这两个 mock 确保不会实际解析
                result = await generator.generate("http://example.com")
                assert "source" in result or "success" in result


class TestSourceGeneratorNetworkFailure:
    """测试网络失败时的兜底逻辑"""

    @pytest.mark.asyncio
    async def test_网络超时使用兼容性兜底(self):
        """当 _fetch_page 返回 None 时，应使用 compat_engine 兜底"""
        generator = SourceGenerator()

        # mock _fetch_page 模拟超时（返回 None, ""）
        generator._fetch_page = AsyncMock(return_value=(None, ""))

        result = await generator.generate("https://example.com")

        # 应有兜底源
        assert "source" in result
        assert result["source"] is not None
        assert "兜底" in result["message"]

    @pytest.mark.asyncio
    async def test_连接失败使用兼容性兜底(self):
        """连接错误时也应使用 compat_engine 兜底"""
        generator = SourceGenerator()

        # mock _fetch_page 模拟连接失败
        generator._fetch_page = AsyncMock(return_value=(None, ""))

        result = await generator.generate("https://novel.example.com")

        # 兜底源应包含 bookSourceUrl
        assert result["source"]["bookSourceUrl"] == "https://novel.example.com"

    @pytest.mark.asyncio
    async def test_HTMLError兜底(self):
        """HTML 解析异常时使用兜底"""
        generator = SourceGenerator()

        # 返回有效的 HTML，但让解析方法抛异常
        generator._fetch_page = AsyncMock(return_value=("<html><body>test</body></html>", "text/html"))

        with patch.object(generator, '_generate_rss_source_from_html', side_effect=Exception("解析错误")):
            result = await generator.generate("https://broken.example.com")

        # 应兜底成功
        assert "source" in result
        assert result["source"] is not None

    @pytest.mark.asyncio
    async def test_兜底后包含源和日志(self):
        """兜底生成后应包含源数据和日志信息"""
        generator = SourceGenerator()
        generator._fetch_page = AsyncMock(return_value=(None, ""))

        result = await generator.generate("https://example.com")

        # 验证兜底源存在
        assert "source" in result
        assert result["source"] is not None
        assert result["source"]["bookSourceUrl"] == "https://example.com"
        # 验证兜底消息
        assert "兜底" in result["message"]
        # 验证 logs 非空
        assert len(result["logs"]) > 0

    @pytest.mark.asyncio
    async def test_logs记录网络失败(self):
        """验证网络失败时 logs 列表记录了相关信息"""
        generator = SourceGenerator()
        generator._fetch_page = AsyncMock(return_value=(None, ""))

        result = await generator.generate("https://fail.example.com")

        # logs 应包含失败和兜底相关消息
        assert len(result["logs"]) > 0
        log_text = " ".join(result["logs"])
        assert "兜底" in log_text or "失败" in log_text


class TestSourceGeneratorRssParsing:
    """测试 RSS/Atom 源生成"""

    @pytest.mark.asyncio
    async def test_RSS_XML成功生成(self):
        """成功解析标准 RSS XML"""
        generator = SourceGenerator()

        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>测试RSS</title>
                <item>
                    <title>文章1</title>
                    <link>https://example.com/1</link>
                </item>
            </channel>
        </rss>"""

        generator._fetch_page = AsyncMock(return_value=(rss_xml, "application/xml"))

        # mock repair_source 避免 ruleContent 类型不兼容问题
        with patch("app.services.generator.compat_engine") as mock_compat:
            mock_compat.repair_source.side_effect = lambda s: {**s, "_fixes": []}
            mock_compat.get_compatibility_score.return_value = {
                "score": 70, "grade": "B", "is_usable": True
            }

            result = await generator.generate("https://rss.example.com/feed.xml")

        assert result["source"] is not None
        assert result["source"]["sourceUrl"] == "https://rss.example.com/feed.xml"
        assert "item" in result["source"]["ruleArticles"]

    @pytest.mark.asyncio
    async def test_Atom_XML成功生成(self):
        """成功解析 Atom Feed XML"""
        generator = SourceGenerator()

        atom_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title>测试Atom</title>
            <entry>
                <title>文章1</title>
                <link href="https://example.com/1"/>
            </entry>
        </feed>"""

        generator._fetch_page = AsyncMock(return_value=(atom_xml, "application/atom+xml"))

        # mock repair_source 避免 ruleContent 类型不兼容问题
        with patch("app.services.generator.compat_engine") as mock_compat:
            mock_compat.repair_source.side_effect = lambda s: {**s, "_fixes": []}
            mock_compat.get_compatibility_score.return_value = {
                "score": 70, "grade": "B", "is_usable": True
            }

            result = await generator.generate("https://atom.example.com/feed", source_name="我的Atom")

        assert result["source"] is not None
        assert result["source"]["sourceName"] == "我的Atom"
        assert "entry" in result["source"]["ruleArticles"]

    @pytest.mark.asyncio
    async def test_content_type检测xml(self):
        """Content-Type 包含 xml 时触发 RSS 解析"""
        generator = SourceGenerator()

        # 非 XML 内容但 Content-Type 为 xml
        generator._fetch_page = AsyncMock(return_value=("<html>data</html>", "application/xml"))

        with patch.object(generator, '_generate_rss_source', new_callable=AsyncMock, return_value={
            "sourceUrl": "https://test.com",
            "sourceName": "XML源",
            "type": 0,
        }):
            result = await generator.generate("https://test.com")

        assert result["source"] is not None

    @pytest.mark.asyncio
    async def test自定义源名称(self):
        """指定 source_name 参数"""
        generator = SourceGenerator()

        rss_xml = '<?xml version="1.0"?><rss><channel><title>Feed标题</title></channel></rss>'
        generator._fetch_page = AsyncMock(return_value=(rss_xml, "application/xml"))

        result = await generator.generate("https://example.com/feed", source_name="自定义名称")

        # 自定义名称应覆盖 Feed 标题
        assert result["source"]["sourceName"] == "自定义名称"


class TestSourceGeneratorBookSource:
    """测试书源生成"""

    @pytest.mark.asyncio
    async def test_book类型源生成(self):
        """source_type=book 时生成书源"""
        generator = SourceGenerator()

        html = """
        <html>
        <head><title>小说网站</title></head>
        <body>
            <form action="/search">
                <input type="text" name="keyword"/>
            </form>
        </body>
        </html>"""

        generator._fetch_page = AsyncMock(return_value=(html, "text/html"))

        with patch.object(generator, '_detect_toc_structure', return_value={
            "chapterList": "div.dd a",
            "chapterName": "text",
            "chapterUrl": "href",
        }):
            result = await generator.generate("https://novel.example.com", source_type="book")

        assert result["source"] is not None
        assert "bookSourceUrl" in result["source"]
        assert result["source"]["bookSourceUrl"] == "https://novel.example.com"


class TestSourceGeneratorFetchPage:
    """通过 generate 间接测试 _fetch_page 的不同返回值"""

    @pytest.mark.asyncio
    async def test_HTTP错误状态码触发兜底(self):
        """HTTP 4xx/5xx 应返回 None，触发兜底"""
        generator = SourceGenerator()

        # _fetch_page 返回 None（模拟 HTTP 错误）
        generator._fetch_page = AsyncMock(return_value=(None, "text/html"))

        result = await generator.generate("https://error.example.com")

        assert "source" in result
        # 兜底源应存在
        assert result["source"] is not None

    @pytest.mark.asyncio
    async def test_成功拉取并解析HTML(self):
        """成功拉取 HTML 并识别 RSS 链接"""
        generator = SourceGenerator()

        html = """
        <html>
        <head>
            <title>博客</title>
            <link rel="alternate" type="application/rss+xml" href="/feed.xml"/>
        </head>
        <body>内容</body>
        </html>"""

        generator._fetch_page = AsyncMock(return_value=(html, "text/html"))

        # 当 HTML 中发现 RSS 链接时，会递归调用 generate
        # 需要阻止递归的无限调用，mock 第二次调用
        rss_xml = '<?xml version="1.0"?><rss><channel><title>RSS</title></channel></rss>'
        fetch_calls = [AsyncMock(return_value=(html, "text/html")),
                       AsyncMock(return_value=(rss_xml, "application/xml"))]

        call_count = 0

        async def mock_fetch(url, *args, **kwargs):
            nonlocal call_count
            if call_count == 0:
                call_count += 1
                return html, "text/html"
            else:
                call_count += 1
                return rss_xml, "application/xml"

        generator._fetch_page = mock_fetch
        result = await generator.generate("https://blog.example.com")

        # 至少应有源生成
        assert "source" in result


class TestSourceGeneratorLogs:
    """测试日志记录"""

    @pytest.mark.asyncio
    async def test_generate记录完整日志(self):
        """验证 generate 方法记录了完整的处理日志"""
        generator = SourceGenerator()
        generator._fetch_page = AsyncMock(return_value=(None, ""))

        result = await generator.generate("https://example.com")

        logs = result.get("logs", [])
        assert len(logs) > 0
        # 第一条日志应包含 URL
        assert "https://example.com" in logs[0]

    @pytest.mark.asyncio
    async def test_成功生成包含评分日志(self):
        """成功路径应包含评分日志"""
        generator = SourceGenerator()
        generator._fetch_page = AsyncMock(return_value=(None, ""))

        result = await generator.generate("https://score.example.com")

        logs = result.get("logs", [])
        log_text = " ".join(logs)
        # 应包含评分相关信息
        assert "评分" in log_text or "兼容性" in log_text


# ==================== MemoryEventBus 测试 ====================

class TestMemoryEventBus:
    """测试内存事件总线"""

    @pytest.mark.asyncio
    async def test_start_stop不崩溃(self):
        """启动和停止不应崩溃"""
        bus = MemoryEventBus()
        await bus.start()
        await bus.stop()
        # 重复停止也不崩溃
        await bus.stop()

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self):
        """订阅事件并发布后处理器被调用"""
        bus = MemoryEventBus()
        received_events = []

        @bus.subscribe(SourceFetchedEvent)
        async def handler(event: SourceFetchedEvent):
            received_events.append(event)

        event = SourceFetchedEvent(subscription_id=1, book_count=10)
        await bus.publish(event)

        # 未启动时直接同步分发
        assert len(received_events) == 1
        assert received_events[0].book_count == 10

    @pytest.mark.asyncio
    async def test_subscribe_decorator(self):
        """通过 subscribe 装饰器注册多个处理器"""
        bus = MemoryEventBus()
        call_log = []

        @bus.subscribe(SourceFetchedEvent)
        async def handler1(event):
            call_log.append("handler1")

        @bus.subscribe(SourceFetchedEvent)
        async def handler2(event):
            call_log.append("handler2")

        event = SourceFetchedEvent()
        await bus.publish(event)

        # 两个处理器都应被调用
        assert "handler1" in call_log
        assert "handler2" in call_log

    @pytest.mark.asyncio
    async def test_不同事件类型隔离(self):
        """不同类型的事件不会互相触发"""
        from app.core.events import SourceDeletedEvent

        bus = MemoryEventBus()
        received = []

        @bus.subscribe(SourceFetchedEvent)
        async def fetched_handler(event):
            received.append("fetched")

        @bus.subscribe(SourceDeletedEvent)
        async def deleted_handler(event):
            received.append("deleted")

        await bus.publish(SourceFetchedEvent())
        assert received == ["fetched"]

        await bus.publish(SourceDeletedEvent())
        assert "deleted" in received

    @pytest.mark.asyncio
    async def test_无订阅者不崩溃(self):
        """发布无人订阅的事件不应崩溃"""
        bus = MemoryEventBus()
        await bus.publish(SourceFetchedEvent())

    @pytest.mark.asyncio
    async def test_处理器异常不影响其他处理器(self):
        """一个处理器抛异常不应影响其他处理器"""
        bus = MemoryEventBus()
        call_log = []

        @bus.subscribe(SourceFetchedEvent)
        async def bad_handler(event):
            call_log.append("bad")
            raise RuntimeError("处理器出错")

        @bus.subscribe(SourceFetchedEvent)
        async def good_handler(event):
            call_log.append("good")

        await bus.publish(SourceFetchedEvent())

        # 两个处理器都应被调用（即使一个报错）
        assert "bad" in call_log
        assert "good" in call_log

    @pytest.mark.asyncio
    async def test_启动后异步分发(self):
        """启动后事件通过队列异步分发"""
        bus = MemoryEventBus()
        received = []

        @bus.subscribe(SourceFetchedEvent)
        async def handler(event):
            received.append(event)

        await bus.start()
        await bus.publish(SourceFetchedEvent(subscription_id=99))

        # 等待队列消费
        import asyncio
        await asyncio.sleep(0.1)

        assert len(received) >= 1
        await bus.stop()

    @pytest.mark.asyncio
    async def test_sync_handler也支持(self):
        """同步处理器也能正常工作"""
        bus = MemoryEventBus()
        received = []

        @bus.subscribe(SourceFetchedEvent)
        def sync_handler(event):  # 注意：非 async
            received.append(event)

        await bus.publish(SourceFetchedEvent())
        assert len(received) == 1


class TestPublishEventConvenience:
    """测试全局便捷函数 publish_event"""

    @pytest.mark.asyncio
    async def test_publish_event_全局便捷函数(self):
        """publish_event 应委托给全局 event_bus"""
        from app.core.events import event_bus, SourceCreatedEvent

        received = []

        @event_bus.subscribe(SourceCreatedEvent)
        async def handler(event):
            received.append(event)

        await publish_event(SourceCreatedEvent(source_url="https://test.com", source_name="测试"))

        assert len(received) == 1
        assert received[0].source_url == "https://test.com"


class TestOnEventDecorator:
    """测试全局 on_event 装饰器"""

    @pytest.mark.asyncio
    async def test_on_event_订阅事件(self):
        """on_event 装饰器应正确订阅事件"""
        from app.core.events import event_bus, SourceStatusChangedEvent, on_event

        received = []

        @on_event(SourceStatusChangedEvent)
        async def on_status_changed(event):
            received.append(event)

        event = SourceStatusChangedEvent(
            source_url="https://a.com",
            old_status="ok",
            new_status="error",
        )
        await publish_event(event)

        assert len(received) == 1
        assert received[0].new_status == "error"
