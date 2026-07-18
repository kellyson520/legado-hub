"""Event-bus infrastructure.

Event payloads live in :mod:`app.domain.events`; this module owns only
delivery, subscription, and logging. The re-exports below keep the historical
import path stable for interface and module adapters.
"""

import asyncio
import inspect
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Type

from app.domain.events import (
    AIAnalysisCompletedEvent,
    AuditEvent,
    ChapterComplementCompletedEvent,
    ChapterComplementRequestedEvent,
    ChapterFetchedFromSourceEvent,
    DictionaryUpdatedEvent,
    DomainEvent,
    FilterRuleTriggeredEvent,
    QuotaExceededEvent,
    QuotaUsageEvent,
    SourceComplementProgressEvent,
    SourceCreatedEvent,
    SourceDeletedEvent,
    SourceFetchedEvent,
    SourceStatusChangedEvent,
    SourceUpdatedEvent,
    SystemNoticeEvent,
    TranslationCompletedEvent,
    TranslationProgressEvent,
    TranslationStartedEvent,
)
from .logging import get_logger

logger = get_logger("event_bus")


class EventBus(ABC):
    """Asynchronous event delivery port implemented by infrastructure."""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, event_type: Type[DomainEvent]) -> Callable:
        raise NotImplementedError

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError


class MemoryEventBus(EventBus):
    """In-process event bus for a single service instance."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._running = False
        self._queue: asyncio.Queue[DomainEvent] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

    def subscribe(self, event_type: Type[DomainEvent]) -> Callable:
        event_name = event_type.__name__

        def decorator(handler: Callable) -> Callable:
            self._handlers.setdefault(event_name, []).append(handler)
            logger.info(
                "事件处理器已注册",
                extra={"action": "event_handler_registered", "event_type": event_name},
            )
            return handler

        return decorator

    async def publish(self, event: DomainEvent) -> None:
        if not self._running:
            await self._dispatch(event)
            return
        await self._queue.put(event)
        logger.debug(
            "事件已入队",
            extra={"action": "event_enqueued", "event_type": event.event_type()},
        )

    async def _dispatch(self, event: DomainEvent) -> None:
        handlers = self._handlers.get(event.event_type(), [])
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception:
                logger.exception(
                    "事件处理器执行失败",
                    extra={
                        "action": "event_handler_error",
                        "event_type": event.event_type(),
                        "handler": getattr(handler, "__name__", repr(handler)),
                    },
                )

    async def _worker(self) -> None:
        logger.info("事件总线已启动", extra={"action": "event_bus_started"})
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("事件总线工作协程异常", extra={"action": "event_bus_worker_error"})
        logger.info("事件总线已停止", extra={"action": "event_bus_stopped"})

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if not self._running:
            return
        # Drain queued events while the worker is still allowed to consume
        # them; setting ``_running`` first can deadlock ``queue.join``.
        await self._queue.join()
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None


event_bus: EventBus = MemoryEventBus()


async def publish_event(event: DomainEvent) -> None:
    await event_bus.publish(event)


def on_event(event_type: Type[DomainEvent]) -> Callable:
    return event_bus.subscribe(event_type)


__all__ = [
    "EventBus",
    "MemoryEventBus",
    "event_bus",
    "publish_event",
    "on_event",
    "DomainEvent",
    "SourceFetchedEvent",
    "SourceStatusChangedEvent",
    "SourceCreatedEvent",
    "SourceUpdatedEvent",
    "SourceDeletedEvent",
    "FilterRuleTriggeredEvent",
    "QuotaUsageEvent",
    "QuotaExceededEvent",
    "AIAnalysisCompletedEvent",
    "ChapterComplementRequestedEvent",
    "ChapterFetchedFromSourceEvent",
    "ChapterComplementCompletedEvent",
    "SourceComplementProgressEvent",
    "AuditEvent",
    "SystemNoticeEvent",
    "TranslationStartedEvent",
    "TranslationCompletedEvent",
    "TranslationProgressEvent",
    "DictionaryUpdatedEvent",
]
