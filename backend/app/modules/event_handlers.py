"""
模块间事件订阅注册

设计原则：
- 每个模块只订阅自己关心的事件
- 不直接调用其他模块的代码
- 通过 event_bus.subscribe() 注册处理器
- 这是模块间唯一的通信方式
"""

from ..core.events import event_bus, on_event
from ..core.events import (
    SourceCreatedEvent, SourceUpdatedEvent, SourceDeletedEvent,
    SourceStatusChangedEvent, SourceFetchedEvent,
    AuditEvent, QuotaExceededEvent, SystemNoticeEvent,
    TranslationStartedEvent, TranslationCompletedEvent,
    TranslationProgressEvent, DictionaryUpdatedEvent
)
from ..core.logging import get_logger

logger = get_logger("modules.events")


# ==================== 翻译模块事件处理 ====================

@on_event(TranslationStartedEvent)
async def handle_translation_started(event: TranslationStartedEvent):
    """翻译开始日志"""
    logger.info(
        f"[Translation] 任务开始: job_id={event.job_id}, book={event.book_name}",
        extra={"action": "translation_started", "job_id": event.job_id}
    )


@on_event(TranslationCompletedEvent)
async def handle_translation_completed(event: TranslationCompletedEvent):
    """翻译完成日志"""
    level = "info" if event.status == "completed" else "warning"
    log_func = getattr(logger, level)
    log_func(
        f"[Translation] 任务完成: job_id={event.job_id}, status={event.status}, "
        f"progress={event.progress}%",
        extra={"action": "translation_completed", "job_id": event.job_id, "status": event.status}
    )


@on_event(TranslationProgressEvent)
async def handle_translation_progress(event: TranslationProgressEvent):
    """翻译进度日志（DEBUG 级别，避免日志过多）"""
    logger.debug(
        f"[Translation] 进度: job_id={event.job_id}, {event.completed_chunks}/{event.total_chunks}",
        extra={"action": "translation_progress", "job_id": event.job_id}
    )


@on_event(DictionaryUpdatedEvent)
async def handle_dictionary_updated(event: DictionaryUpdatedEvent):
    """词典更新日志"""
    logger.info(
        f"[Translation] 词典更新: book={event.book_name}, "
        f"new_entries={len(event.new_entries)}, total={event.total_entries}",
        extra={
            "action": "dictionary_updated",
            "book_url": event.book_url,
            "total_entries": event.total_entries
        }
    )


# ==================== 审计模块（订阅所有关键事件）====================

@on_event(SourceCreatedEvent)
async def audit_source_created(event: SourceCreatedEvent):
    """审计：记录源创建"""
    logger.info(
        f"[Audit] 源创建: {event.source_name} ({event.source_type})",
        extra={"action": "source_created", "source_url": event.source_url}
    )


@on_event(SourceDeletedEvent)
async def audit_source_deleted(event: SourceDeletedEvent):
    """审计：记录源删除"""
    logger.info(
        f"[Audit] 源删除: {event.source_name} ({event.source_type})",
        extra={"action": "source_deleted", "source_url": event.source_url}
    )


@on_event(SourceStatusChangedEvent)
async def audit_source_status(event: SourceStatusChangedEvent):
    """审计：记录源状态变更"""
    if event.new_status == "error":
        logger.warning(
            f"[Audit] 源异常: {event.source_name} -> {event.new_status}",
            extra={"action": "source_error", "source_url": event.source_url}
        )


# ==================== 统计模块 ====================

@on_event(SourceFetchedEvent)
async def stats_source_fetched(event: SourceFetchedEvent):
    """统计：记录订阅拉取结果"""
    logger.info(
        f"[Stats] 订阅拉取: {event.subscription_name} 书源={event.book_count} 订阅={event.rss_count}",
        extra={"action": "fetch_completed", "sub_id": event.subscription_id}
    )


# ==================== 告警模块 ====================

@on_event(QuotaExceededEvent)
async def alert_quota_exceeded(event: QuotaExceededEvent):
    """告警：配额超限"""
    logger.warning(
        f"[Alert] 配额超限: key={event.api_key_id} {event.metric} {event.used}/{event.limit}",
        extra={"action": "quota_alert", "api_key_id": event.api_key_id}
    )


@on_event(SystemNoticeEvent)
async def handle_system_notice(event: SystemNoticeEvent):
    """系统通知"""
    level_map = {"info": logger.info, "warning": logger.warning, "error": logger.error}
    log_func = level_map.get(event.level, logger.info)
    log_func(f"[Notice] {event.title}: {event.content}")


# ==================== 注册入口 ====================

def register_all_handlers():
    """注册所有事件处理器（在应用启动时调用）"""
    # 装饰器已经自动注册了处理器
    # 此函数用于确保模块被加载
    logger.info("[Modules] 事件处理器注册完成")
