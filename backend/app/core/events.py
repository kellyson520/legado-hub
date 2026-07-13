"""
事件总线基础设施 - 模块间解耦通信的核心

设计原则：
- 模块 A 不知道模块 B 的存在，只发布事件
- 模块 B 订阅感兴趣的事件，异步处理
- 支持内存模式（小 VPS 零依赖）和 Redis 模式（分布式）

使用方式：
    # 模块 A：发布事件
    await event_bus.publish(SourceFetchedEvent(sub_id=1, count=10))
    
    # 模块 B：订阅事件
    @event_bus.subscribe(SourceFetchedEvent)
    async def on_source_fetched(event: SourceFetchedEvent):
        await update_stats(event.sub_id, event.count)
"""

import asyncio
import inspect
from typing import Any, Callable, Dict, List, Type, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from abc import ABC, abstractmethod

from .logging import get_logger

logger = get_logger("event_bus")


# ==================== 事件基类 ====================

@dataclass
class DomainEvent:
    """领域事件基类"""
    event_id: str = field(default_factory=lambda: f"evt_{datetime.utcnow().timestamp()}")
    timestamp: datetime = field(default_factory=datetime.utcnow)
    trace_id: Optional[str] = None
    
    def event_type(self) -> str:
        return self.__class__.__name__


# ==================== 预定义领域事件 ====================

@dataclass
class SourceFetchedEvent(DomainEvent):
    """订阅源拉取完成事件"""
    subscription_id: int = 0
    subscription_name: str = ""
    book_count: int = 0
    rss_count: int = 0
    status: str = "success"  # success, error
    message: str = ""


@dataclass
class SourceStatusChangedEvent(DomainEvent):
    """源状态变更事件"""
    source_url: str = ""
    source_name: str = ""
    source_type: str = ""  # book, rss
    old_status: str = ""
    new_status: str = ""
    error_msg: Optional[str] = None


@dataclass
class SourceCreatedEvent(DomainEvent):
    """新源创建事件"""
    source_url: str = ""
    source_name: str = ""
    source_type: str = ""
    created_by: Optional[int] = None


@dataclass
class SourceUpdatedEvent(DomainEvent):
    """源更新事件"""
    source_url: str = ""
    source_name: str = ""
    source_type: str = ""
    changed_fields: List[str] = field(default_factory=list)


@dataclass
class SourceDeletedEvent(DomainEvent):
    """源删除事件"""
    source_url: str = ""
    source_name: str = ""
    source_type: str = ""


@dataclass
class FilterRuleTriggeredEvent(DomainEvent):
    """过滤规则触发事件"""
    rule_id: int = 0
    rule_name: str = ""
    source_url: str = ""
    source_name: str = ""
    match_field: str = ""


@dataclass
class QuotaUsageEvent(DomainEvent):
    """配额使用事件"""
    api_key_id: int = 0
    metric: str = ""  # fetch_count, ai_chars, storage_mb
    amount: int = 0
    total_used: int = 0
    limit: int = 0


@dataclass
class QuotaExceededEvent(DomainEvent):
    """配额超限告警事件"""
    api_key_id: int = 0
    metric: str = ""
    used: int = 0
    limit: int = 0


@dataclass
class AIAnalysisCompletedEvent(DomainEvent):
    """AI 分析完成事件"""
    analysis_type: str = ""  # character, world, storyline, chat, fix, review
    book_url: str = ""
    book_name: str = ""
    result_id: int = 0
    chars_consumed: int = 0
    status: str = "success"


# ==================== 书源互补领域事件 ====================

@dataclass
class ChapterComplementRequestedEvent(DomainEvent):
    """章节互补请求事件 - 触发多源并行抓取"""
    job_id: str = ""
    book_name: str = ""
    chapter_title: str = ""
    chapter_num: int = 0
    source_urls: List[str] = field(default_factory=list)  # 要并行请求的书源列表
    priority: str = "normal"  # low / normal / high


@dataclass
class ChapterFetchedFromSourceEvent(DomainEvent):
    """单个书源章节抓取完成事件"""
    job_id: str = ""
    source_url: str = ""
    source_name: str = ""
    chapter_title: str = ""
    chapter_num: int = 0
    content: str = ""
    word_count: int = 0
    success: bool = True
    error: Optional[str] = None
    response_time_ms: int = 0


@dataclass
class ChapterComplementCompletedEvent(DomainEvent):
    """章节互补完成事件 - 所有源抓取+对比合并完成"""
    job_id: str = ""
    book_name: str = ""
    chapter_title: str = ""
    chapter_num: int = 0
    total_sources: int = 0
    successful_sources: int = 0
    final_content: str = ""
    final_word_count: int = 0
    quality_score: float = 0.0
    source_contributions: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "success"  # success / partial / failed
    merged_from: List[str] = field(default_factory=list)  # 参与合并的 source_url 列表


@dataclass
class SourceComplementProgressEvent(DomainEvent):
    """书源互补进度事件"""
    job_id: str = ""
    total_sources: int = 0
    completed_sources: int = 0
    failed_sources: int = 0
    progress: float = 0.0
    status: str = "running"  # running / completed / failed


@dataclass
class AuditEvent(DomainEvent):
    """审计事件"""
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    user_id: Optional[int] = None
    api_key_id: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: Optional[str] = None


@dataclass
class SystemNoticeEvent(DomainEvent):
    """系统通知事件"""
    level: str = "info"  # info, warning, error
    title: str = ""
    content: str = ""
    target: str = "all"  # all, admin, user


# ==================== 翻译领域事件 ====================

@dataclass
class TranslationStartedEvent(DomainEvent):
    """翻译开始事件"""
    job_id: str = ""
    book_url: str = ""
    book_name: str = ""
    chapter_title: str = ""
    total_chunks: int = 0


@dataclass
class TranslationCompletedEvent(DomainEvent):
    """翻译完成事件"""
    job_id: str = ""
    book_url: str = ""
    book_name: str = ""
    chapter_title: str = ""
    status: str = "completed"  # completed, partial, failed
    progress: float = 0.0


@dataclass
class TranslationProgressEvent(DomainEvent):
    """翻译进度事件"""
    job_id: str = ""
    completed_chunks: int = 0
    total_chunks: int = 0
    progress: float = 0.0


@dataclass
class DictionaryUpdatedEvent(DomainEvent):
    """词典更新事件"""
    book_url: str = ""
    book_name: str = ""
    new_entries: Dict[str, Any] = field(default_factory=dict)
    total_entries: int = 0


# ==================== 事件总线接口 ====================

class EventBus(ABC):
    """事件总线抽象接口"""
    
    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """发布事件"""
        pass
    
    @abstractmethod
    def subscribe(self, event_type: Type[DomainEvent]) -> Callable:
        """订阅事件（装饰器）"""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """启动事件总线"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """停止事件总线"""
        pass


# ==================== 内存事件总线实现 ====================

class MemoryEventBus(EventBus):
    """
    内存事件总线 - 小 VPS 友好，零外部依赖
    
    特点：
    - 同进程内异步分发
    - 失败不影响发布者
    - 无需 Redis 等外部服务
    """
    
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._running = False
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
    
    def subscribe(self, event_type: Type[DomainEvent]) -> Callable:
        """装饰器：订阅指定类型的事件"""
        event_name = event_type.__name__
        
        def decorator(handler: Callable) -> Callable:
            if event_name not in self._handlers:
                self._handlers[event_name] = []
            self._handlers[event_name].append(handler)
            logger.info(f"[EventBus] 注册处理器: {event_name} -> {handler.__name__}")
            return handler
        
        return decorator
    
    async def publish(self, event: DomainEvent) -> None:
        """发布事件到队列"""
        if not self._running:
            # 如果总线未启动，直接同步处理
            await self._dispatch(event)
            return
        
        await self._queue.put(event)
        logger.debug(f"[EventBus] 事件入队: {event.event_type()}")
    
    async def _dispatch(self, event: DomainEvent) -> None:
        """分发事件到所有订阅者"""
        event_name = event.event_type()
        handlers = self._handlers.get(event_name, [])
        
        if not handlers:
            logger.debug(f"[EventBus] 无订阅者: {event_name}")
            return
        
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(
                    f"[EventBus] 处理器异常: {handler.__name__} 处理 {event_name} 失败: {e}",
                    exc_info=True
                )
                # 一个处理器失败不影响其他处理器
    
    async def _worker(self) -> None:
        """后台工作协程：消费事件队列"""
        logger.info("[EventBus] 事件处理器已启动")
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[EventBus] 工作协程异常: {e}", exc_info=True)
        logger.info("[EventBus] 事件处理器已停止")
    
    async def start(self) -> None:
        """启动事件总线"""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
    
    async def stop(self) -> None:
        """停止事件总线"""
        if not self._running:
            return
        self._running = False
        if self._worker_task:
            # 等待队列处理完毕
            await self._queue.join()
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass


# ==================== 全局实例 ====================

event_bus: EventBus = MemoryEventBus()


async def publish_event(event: DomainEvent) -> None:
    """全局便捷函数：发布事件"""
    await event_bus.publish(event)


def on_event(event_type: Type[DomainEvent]) -> Callable:
    """全局便捷函数：订阅事件（装饰器）"""
    return event_bus.subscribe(event_type)
