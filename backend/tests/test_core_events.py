"""
events.py 单元测试

覆盖事件总线的核心功能：
- MemoryEventBus 的 start/stop
- subscribe 装饰器注册处理器
- publish 异步发布事件
- on_event 和 publish_event 便捷函数
- 事件类（SourceCreatedEvent, QuotaExceededEvent, SystemNoticeEvent, AIAnalysisCompletedEvent）
- 处理器异常不影响其他处理器
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch


class TestDomainEvent:
    """领域事件基类和预定义事件测试"""

    def test_domain_event_has_event_id(self):
        """验证事件有唯一 event_id"""
        from app.core.events import DomainEvent
        event = DomainEvent()
        assert event.event_id.startswith("evt_")

    def test_domain_event_has_timestamp(self):
        """验证事件有时间戳"""
        from app.core.events import DomainEvent
        event = DomainEvent()
        assert event.timestamp is not None

    def test_event_type_returns_class_name(self):
        """验证 event_type() 返回类名"""
        from app.core.events import DomainEvent
        event = DomainEvent()
        assert event.event_type() == "DomainEvent"

    def test_source_created_event_fields(self):
        """验证 SourceCreatedEvent 的字段"""
        from app.core.events import SourceCreatedEvent
        event = SourceCreatedEvent(
            source_url="https://example.com",
            source_name="测试书源",
            source_type="book"
        )
        assert event.source_url == "https://example.com"
        assert event.source_name == "测试书源"
        assert event.source_type == "book"
        assert event.event_type() == "SourceCreatedEvent"

    def test_quota_exceeded_event_fields(self):
        """验证 QuotaExceededEvent 的字段"""
        from app.core.events import QuotaExceededEvent
        event = QuotaExceededEvent(
            api_key_id=1,
            metric="fetch_count",
            used=500,
            limit=500
        )
        assert event.api_key_id == 1
        assert event.metric == "fetch_count"
        assert event.used == 500
        assert event.limit == 500

    def test_system_notice_event_fields(self):
        """验证 SystemNoticeEvent 的字段"""
        from app.core.events import SystemNoticeEvent
        event = SystemNoticeEvent(
            level="warning",
            title="系统维护通知",
            content="今晚 22:00 进行系统维护"
        )
        assert event.level == "warning"
        assert event.title == "系统维护通知"
        assert event.content == "今晚 22:00 进行系统维护"

    def test_ai_analysis_completed_event_fields(self):
        """验证 AIAnalysisCompletedEvent 的字段"""
        from app.core.events import AIAnalysisCompletedEvent
        event = AIAnalysisCompletedEvent(
            analysis_type="character",
            book_url="https://example.com/book/1",
            book_name="测试小说",
            chars_consumed=5000,
            status="success"
        )
        assert event.analysis_type == "character"
        assert event.book_name == "测试小说"
        assert event.chars_consumed == 5000
        assert event.status == "success"


class TestMemoryEventBusSubscribe:
    """subscribe 装饰器测试"""

    def test_subscribe_registers_handler(self, fresh_event_bus):
        """验证 subscribe 装饰器注册处理器"""
        from app.core.events import SourceCreatedEvent
        handler_called = False

        @fresh_event_bus.subscribe(SourceCreatedEvent)
        async def on_created(event):
            nonlocal handler_called
            handler_called = True

        # 验证处理器已注册到事件总线
        assert "SourceCreatedEvent" in fresh_event_bus._handlers
        assert len(fresh_event_bus._handlers["SourceCreatedEvent"]) == 1

    def test_subscribe_multiple_handlers(self, fresh_event_bus):
        """验证同一事件可以注册多个处理器"""
        from app.core.events import SourceCreatedEvent

        @fresh_event_bus.subscribe(SourceCreatedEvent)
        async def handler_a(event):
            pass

        @fresh_event_bus.subscribe(SourceCreatedEvent)
        async def handler_b(event):
            pass

        assert len(fresh_event_bus._handlers["SourceCreatedEvent"]) == 2


class TestMemoryEventBusPublish:
    """publish 发布事件测试"""

    async def test_publish_without_start_dispatches_directly(self, fresh_event_bus):
        """验证未启动时直接分发（同步处理）"""
        from app.core.events import SourceCreatedEvent
        received_events = []

        @fresh_event_bus.subscribe(SourceCreatedEvent)
        async def handler(event):
            received_events.append(event)

        event = SourceCreatedEvent(source_url="https://example.com", source_name="测试")
        await fresh_event_bus.publish(event)
        assert len(received_events) == 1
        assert received_events[0].source_url == "https://example.com"

    async def test_publish_no_subscribers_no_error(self, fresh_event_bus):
        """验证发布无人订阅的事件不报错"""
        from app.core.events import SourceCreatedEvent
        event = SourceCreatedEvent()
        # 不注册任何处理器
        await fresh_event_bus.publish(event)  # 不应抛出异常

    async def test_publish_with_started_bus(self, started_event_bus):
        """验证启动后发布事件通过队列异步处理"""
        from app.core.events import QuotaExceededEvent
        received_events = []

        @started_event_bus.subscribe(QuotaExceededEvent)
        async def handler(event):
            received_events.append(event)

        event = QuotaExceededEvent(api_key_id=1, metric="ai_chars", used=100, limit=100)
        await started_event_bus.publish(event)
        # 等待事件被消费
        await asyncio.sleep(0.2)
        assert len(received_events) == 1

    async def test_handler_failure_does_not_block_others(self, fresh_event_bus):
        """验证一个处理器异常不影响其他处理器"""
        from app.core.events import SystemNoticeEvent
        results = []

        @fresh_event_bus.subscribe(SystemNoticeEvent)
        async def handler_fails(event):
            raise RuntimeError("处理器A异常")

        @fresh_event_bus.subscribe(SystemNoticeEvent)
        async def handler_ok(event):
            results.append("handler_ok_called")

        event = SystemNoticeEvent(level="info", title="测试", content="内容")
        await fresh_event_bus.publish(event)
        assert "handler_ok_called" in results


class TestMemoryEventBusStartStop:
    """start/stop 生命周期测试"""

    async def test_start_sets_running_true(self, fresh_event_bus):
        """验证启动后 _running 为 True"""
        await fresh_event_bus.start()
        assert fresh_event_bus._running is True
        await fresh_event_bus.stop()

    async def test_stop_sets_running_false(self, fresh_event_bus):
        """验证停止后 _running 为 False"""
        await fresh_event_bus.start()
        await fresh_event_bus.stop()
        assert fresh_event_bus._running is False

    async def test_double_start_is_idempotent(self, fresh_event_bus):
        """验证重复启动不会创建多个 worker"""
        await fresh_event_bus.start()
        await fresh_event_bus.start()
        assert fresh_event_bus._running is True
        await fresh_event_bus.stop()

    async def test_double_stop_is_idempotent(self, fresh_event_bus):
        """验证重复停止不会报错"""
        await fresh_event_bus.start()
        await fresh_event_bus.stop()
        await fresh_event_bus.stop()  # 不应抛出异常

    async def test_stop_drains_multiple_queued_events(self, fresh_event_bus):
        from app.core.events import SourceCreatedEvent

        received = []

        @fresh_event_bus.subscribe(SourceCreatedEvent)
        async def handler(event):
            received.append(event.source_url)

        await fresh_event_bus.start()
        for index in range(4):
            await fresh_event_bus.publish(SourceCreatedEvent(source_url=f"https://{index}.example"))

        await fresh_event_bus.stop()

        assert received == [f"https://{index}.example" for index in range(4)]


class TestPublishEvent:
    """publish_event 全局便捷函数测试"""

    async def test_publish_event_dispatches(self):
        """验证 publish_event 通过全局 event_bus 发布"""
        from app.core.events import (
            publish_event, event_bus,
            SourceCreatedEvent
        )
        # 使用全局 event_bus 并注册临时处理器
        received = []

        @event_bus.subscribe(SourceCreatedEvent)
        async def handler(event):
            received.append(event)

        event = SourceCreatedEvent(source_url="https://example.com", source_name="全局发布测试")
        await publish_event(event)
        assert len(received) == 1
        assert received[0].source_name == "全局发布测试"

        # 清理处理器避免影响其他测试
        event_bus._handlers["SourceCreatedEvent"] = []


class TestOnEvent:
    """on_event 全局装饰器测试"""

    def test_on_event_registers_to_global_bus(self):
        """验证 on_event 装饰器注册到全局 event_bus"""
        from app.core.events import on_event, event_bus, SystemNoticeEvent

        @on_event(SystemNoticeEvent)
        async def handler(event):
            pass

        assert "SystemNoticeEvent" in event_bus._handlers
        # 清理
        event_bus._handlers["SystemNoticeEvent"] = []
