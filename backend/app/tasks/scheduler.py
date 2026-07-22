"""
定时任务调度器

职责：
- 异步执行定时任务（不再使用 asyncio.run 反模式）
- 统一日志（每个任务独立 trace）
- 异常隔离（单个任务失败不影响其他任务）
- 发布领域事件
"""

import asyncio
import inspect
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..core.config import settings
from ..core.logging import get_logger, set_log_context, clear_log_context
from ..core.events import publish_event, SourceFetchedEvent, SystemNoticeEvent
from ..infrastructure.persistence.factory import (
    build_auth_repository,
    build_event_delivery_service,
    build_novel_analysis_pipeline_service,
    build_novel_analysis_task_service,
    build_maintenance_service,
    build_source_repository,
    build_source_health_admin_service,
    build_system_settings_service,
)
from ..infrastructure.crawler.source_fetcher import SourceFetcher, SourceChecker

logger = get_logger("scheduler")
scheduler = BackgroundScheduler()
SMART_SOURCE_HEALTH_KEYWORDS = ("捞尸人", "斗罗大陆", "剑来")


def _safe_async_run(coro):
    """安全执行异步协程（用于 APScheduler 同步上下文中调用异步代码）"""
    try:
        loop = asyncio.get_running_loop()
        # 已有事件循环，用 nest
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=300)
    except RuntimeError:
        return asyncio.run(coro)


def job_fetch_subscriptions():
    """定时拉取所有订阅"""
    job_name = "fetch_subscriptions"
    set_log_context(trace_id=f"job_{datetime.utcnow().timestamp():.0f}")
    logger.info(f"[定时任务] 开始拉取订阅", extra={"action": "job_start", "job": job_name})

    async def _do():
        source_repository = build_source_repository()
        subs = (await source_repository.list_subscriptions(enabled_only=True))
        logger.info(f"[定时任务] 共 {len(subs)} 个活跃订阅", extra={"action": job_name, "count": len(subs)})

        success_count = 0
        fail_count = 0
        async with SourceFetcher(source_repository=source_repository) as fetcher:
            for sub in subs:
                try:
                    result = await fetcher.fetch_subscription(sub.id)
                    if result.get("success"):
                        success_count += 1
                    else:
                        fail_count += 1
                        logger.warning(
                            f"[定时任务] 订阅拉取失败: {sub.name}: {result.get('message')}",
                            extra={"action": job_name, "sub_id": sub.id, "sub_name": sub.name}
                        )
                except Exception as e:
                    fail_count += 1
                    logger.error(
                        f"[定时任务] 订阅异常: {sub.name} - {e}",
                        extra={"action": job_name, "sub_id": sub.id, "sub_name": sub.name, "error": str(e)},
                        exc_info=True
                    )

        logger.info(
            f"[定时任务] 拉取完成: 成功={success_count}, 失败={fail_count}",
            extra={"action": "job_end", "job": job_name, "success_count": success_count, "fail_count": fail_count}
        )

    try:
        _safe_async_run(_do())
    except Exception as e:
        logger.error(f"[定时任务] 拉取任务全局异常: {e}", extra={"action": "job_error", "job": job_name}, exc_info=True)
    finally:
        clear_log_context()


def job_check_sources():
    """定时检查源可用性"""
    job_name = "check_sources"
    set_log_context(trace_id=f"job_{datetime.utcnow().timestamp():.0f}")
    logger.info(f"[定时任务] 开始可用性检查", extra={"action": "job_start", "job": job_name})

    async def _do():
        from ..core.redis_client import redis_client

        repo = build_source_repository()
        checker = SourceChecker()

        checked = 0
        failed = 0

        # 书源
        book_sources, book_total = await repo.list_book_sources(enabled_only=True, page=1, page_size=50)
        logger.info(f"[定时任务] 待检书源: {len(book_sources)} 个", extra={"action": job_name, "type": "book", "count": len(book_sources)})

        async with checker:
            for s in book_sources:
                cached = await redis_client.get_cached_source_check(s.bookSourceUrl)
                if cached:
                    continue

                data = s.__dict__.copy()
                result = await checker.check_book_source(data)
                await repo.update_book_source_status(s.bookSourceUrl, result["status"], result.get("errorMsg"))
                await redis_client.cache_source_check(s.bookSourceUrl, result, expire=3600)

                checked += 1
                if result["status"] == "error":
                    failed += 1

        # 订阅源
        rss_sources, rss_total = await repo.list_rss_sources(enabled_only=True, page=1, page_size=50)
        logger.info(f"[定时任务] 待检订阅源: {len(rss_sources)} 个", extra={"action": job_name, "type": "rss", "count": len(rss_sources)})

        for s in rss_sources:
            cached = await redis_client.get_cached_source_check(s.sourceUrl)
            if cached:
                continue

            data = s.__dict__.copy()
            result = await checker.check_rss_source(data)
            await repo.update_rss_source_status(s.sourceUrl, result["status"], result.get("errorMsg"))
            await redis_client.cache_source_check(s.sourceUrl, result, expire=3600)

            checked += 1
            if result["status"] == "error":
                failed += 1

        logger.info(
            f"[定时任务] 检查完成: 已检={checked}, 失败={failed}",
            extra={"action": "job_end", "job": job_name, "checked": checked, "failed": failed}
        )

    try:
        _safe_async_run(_do())
    except Exception as e:
        logger.error(f"[定时任务] 检查任务全局异常: {e}", extra={"action": "job_error", "job": job_name}, exc_info=True)
    finally:
        clear_log_context()


def job_probe_source_health():
    """按最久未探测优先级执行有界的 Legado 全链路健康探测。"""
    job_name = "probe_source_health"
    if not settings.SOURCE_HEALTH_PROBE_WORKER_ENABLED:
        logger.info("[定时任务] 智能书源探测已关闭", extra={"action": "job_skipped", "job": job_name})
        return

    set_log_context(trace_id=f"job_{datetime.utcnow().timestamp():.0f}")
    try:
        result = _safe_async_run(
            run_smart_source_health_probe_job(
                limit=settings.SOURCE_HEALTH_PROBE_BATCH_SIZE,
                keyword_samples=list(SMART_SOURCE_HEALTH_KEYWORDS),
            )
        )
        logger.info(
            "[定时任务] 智能书源探测完成",
            extra={
                "action": "job_end",
                "job": job_name,
                "total": result.get("total", 0) if isinstance(result, dict) else 0,
            },
        )
    except Exception as exc:
        logger.error(
            f"[定时任务] 智能书源探测异常: {exc}",
            extra={"action": "job_error", "job": job_name, "error": str(exc)},
            exc_info=True,
        )
    finally:
        clear_log_context()


def job_cleanup_ephemeral_sources():
    """Remove expired tenant-scoped source sandboxes."""
    job_name = "cleanup_ephemeral_sources"
    set_log_context(trace_id=f"job_{datetime.utcnow().timestamp():.0f}")
    try:
        deleted = _safe_async_run(run_ephemeral_source_cleanup_job())
        logger.info(
            "[定时任务] 临时书源清理完成",
            extra={"action": "job_end", "job": job_name, "deleted": deleted},
        )
    except Exception as exc:
        logger.exception(
            "[定时任务] 临时书源清理异常",
            extra={"action": "job_error", "job": job_name},
        )
    finally:
        clear_log_context()


def job_mark_stale_sources():
    """标记长期失效的源"""
    job_name = "mark_stale_sources"
    set_log_context(trace_id=f"job_{datetime.utcnow().timestamp():.0f}")
    logger.info(f"[定时任务] 开始清理失效源", extra={"action": "job_start", "job": job_name})

    async def _do():
        stale_threshold = datetime.utcnow() - timedelta(days=7)
        try:
            disabled = await build_maintenance_service().disable_stale_sources(
                cutoff=stale_threshold,
                limit=100,
            )
            for source in disabled:
                logger.info(
                    "禁用长期失效书源",
                    extra={
                        "action": job_name,
                        "source_url": source.get("source_url", ""),
                        "source_type": source.get("source_type", ""),
                    },
                )
            total = len(disabled)
            if total > 0:
                logger.info("自动禁用长期失效源", extra={"action": "job_end", "job": job_name, "disabled": total})
                await publish_event(SystemNoticeEvent(
                    level="warning",
                    title="失效源清理",
                    content=f"已自动禁用 {total} 个连续 7 天不可用的源"
                ))
        except Exception as e:
            logger.error(f"[定时任务] 失效源清理异常: {e}", extra={"action": "job_error", "job": job_name, "error": str(e)}, exc_info=True)

    try:
        _safe_async_run(_do())
    except Exception as e:
        logger.error(f"[定时任务] 清理任务全局异常: {e}", extra={"action": "job_error", "job": job_name}, exc_info=True)
    finally:
        clear_log_context()


def job_reset_daily_quota():
    """每日重置配额"""
    job_name = "reset_quota"
    set_log_context(trace_id=f"job_{datetime.utcnow().timestamp():.0f}")
    logger.info(f"[定时任务] 开始重置日配额", extra={"action": "job_start", "job": job_name})

    async def _do():
        try:
            count = await build_maintenance_service().reset_daily_quotas()
            logger.info(f"[定时任务] 已重置 {count} 个 API Key 配额", extra={"action": "job_end", "job": job_name, "count": count})
        except Exception as e:
            logger.error(f"[定时任务] 配额重置异常: {e}", extra={"action": "job_error", "job": job_name, "error": str(e)}, exc_info=True)

    try:
        _safe_async_run(_do())
    except Exception as e:
        logger.error(f"[定时任务] 配额重置全局异常: {e}", extra={"action": "job_error", "job": job_name}, exc_info=True)
    finally:
        clear_log_context()


def job_sync_quota_to_db():
    """配额同步到数据库"""
    job_name = "sync_quota"
    set_log_context(trace_id=f"job_{datetime.utcnow().timestamp():.0f}")

    async def _do():
        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            synced = await build_maintenance_service().sync_quotas(date=today)
            if synced > 0:
                logger.info(f"[定时任务] 配额同步: {synced} 个 key", extra={"action": job_name, "synced": synced})
        except Exception as e:
            logger.error(f"[定时任务] 配额同步异常: {e}", extra={"action": "job_error", "job": job_name, "error": str(e)}, exc_info=True)

    try:
        _safe_async_run(_do())
    except Exception as e:
        logger.error(f"[定时任务] 配额同步全局异常: {e}", extra={"action": "job_error", "job": job_name}, exc_info=True)
    finally:
        clear_log_context()


def job_archive_audit_logs():
    """归档过期审计日志"""
    job_name = "archive_logs"
    set_log_context(trace_id=f"job_{datetime.utcnow().timestamp():.0f}")

    async def _do():
        repo = build_auth_repository()
        deleted = await repo.delete_old_audit_events(days=90)
        if deleted > 0:
            logger.info(f"[定时任务] 归档审计日志: 删除 {deleted} 条", extra={"action": job_name, "deleted": deleted})
        else:
            logger.debug(f"[定时任务] 无需归档", extra={"action": job_name})

    try:
        _safe_async_run(_do())
    except Exception as e:
        logger.error(f"[定时任务] 日志归档异常: {e}", extra={"action": "job_error", "job": job_name, "error": str(e)}, exc_info=True)
    finally:
        clear_log_context()


def job_process_novel_analysis_tasks():
    """Run a bounded batch of evidence-first analysis tasks when automation permits it."""
    job_name = "novel_analysis_tasks"
    set_log_context(trace_id=f"job_{datetime.utcnow().timestamp():.0f}")

    async def _do():
        settings = build_system_settings_service()
        automation_section = settings.get_section("agents", "automation")
        automation = automation_section.get("value", {}) if isinstance(automation_section, dict) else {}
        if not (
            bool(automation.get("enabled", True))
            and bool(automation.get("background_incremental_enabled", False))
            and not bool(automation.get("emergency_pause", False))
        ):
            logger.info(
                "[定时任务] 小说分析自动化未启用或已暂停",
                extra={"action": job_name, "status": "skipped"},
            )
            return

        budgets_section = settings.get_section("agents", "budgets")
        budgets = budgets_section.get("value", {}) if isinstance(budgets_section, dict) else {}
        limit = min(max(int(budgets.get("max_concurrent_tasks", 1)), 1), 8)
        task_service = build_novel_analysis_task_service()
        pipeline = build_novel_analysis_pipeline_service()
        for _ in range(limit):
            task = task_service.lease_next()
            if task is None:
                return
            try:
                result = await pipeline.process_task(task, tenant_id=task.tenant_id)
                if result.reasons and not result.claim_ids:
                    task_service.block(
                        task.id,
                        tenant_id=task.tenant_id,
                        reason="; ".join(result.reasons),
                    )
                    continue
                task_service.complete(task.id, tenant_id=task.tenant_id, result=result)
            except Exception as exc:
                task_service.block(
                    task.id,
                    tenant_id=task.tenant_id,
                    reason=_sanitize_analysis_task_error(exc),
                )
                logger.exception(
                    "[定时任务] 小说分析任务已阻断",
                    extra={"action": job_name, "task_id": task.id},
                )

    try:
        _safe_async_run(_do())
    except Exception as exc:
        logger.exception(
            "[定时任务] 小说分析调度异常: %s",
            exc,
            extra={"action": "job_error", "job": job_name},
        )
    finally:
        clear_log_context()


def _sanitize_analysis_task_error(exc: Exception) -> str:
    message = str(exc)
    import re

    message = re.sub(r"(?i)(bearer|api[_ -]?key)\s*[:=]?\s*[^\s,;]+", r"\1 [redacted]", message)
    return message[:500] or exc.__class__.__name__


# ==================== 调度注册 ====================

JOBS = [
    ("fetch_subscriptions", "0 */2 * * *", job_fetch_subscriptions, "每2小时拉取订阅"),
    ("check_sources", "0 */4 * * *", job_check_sources, "每4小时检查可用性"),
    ("probe_source_health", "*/30 * * * *", job_probe_source_health, "每30分钟智能探测书源"),
    ("cleanup_ephemeral_sources", "*/15 * * * *", job_cleanup_ephemeral_sources, "每15分钟清理临时书源"),
    ("mark_stale_sources", "0 3 * * *", job_mark_stale_sources, "每天3点清理失效源"),
    ("reset_daily_quota", "0 0 * * *", job_reset_daily_quota, "每天0点重置配额"),
    ("sync_quota_to_db", "*/30 * * * *", job_sync_quota_to_db, "每30分钟同步配额"),
    ("archive_audit_logs", "0 2 * * 0", job_archive_audit_logs, "每周日2点归档日志"),
    ("novel_analysis_tasks", "*/5 * * * *", job_process_novel_analysis_tasks, "每5分钟处理证据分析任务"),
]


def start_scheduler(job_ids: set[str] | None = None):
    """启动调度器；可按任务 ID 限定应用内需要的任务。"""
    registered_count = 0
    for job_id, cron, func, desc in JOBS:
        if job_ids is not None and job_id not in job_ids:
            continue
        scheduler.add_job(func, CronTrigger.from_crontab(cron), id=job_id, replace_existing=True)
        logger.info(f"[调度器] 注册任务: {job_id} ({cron}) - {desc}")
        registered_count += 1

    scheduler.start()
    logger.info(f"[调度器] 启动完成, 共 {registered_count} 个任务")


def stop_scheduler():
    scheduler.shutdown()
    logger.info("[调度器] 已停止")


async def run_source_runtime_health_job() -> list[dict]:
    from ..infrastructure.persistence.factory import build_source_health_service

    service = build_source_health_service()
    return await service.verify_published_versions()


async def run_ephemeral_source_cleanup_job() -> int:
    repo = build_source_repository()
    cleanup = getattr(repo, "delete_expired_ephemeral_book_sources", None)
    if not callable(cleanup):
        return 0
    return int(await cleanup() or 0)


async def run_source_health_probe_job(
    source_ids: list[int],
    keyword_samples: list[str],
    probe_mode: str = "full_chain",
) -> dict:
    service = build_source_health_admin_service()
    try:
        return await service.probe_book_sources(
            source_ids,
            keyword_samples=keyword_samples,
            probe_mode=probe_mode,
        )
    finally:
        await _close_async_service(service)


async def run_smart_source_health_probe_job(
    limit: int = 10,
    keyword_samples: list[str] | None = None,
    probe_mode: str = "full_chain",
) -> dict:
    service = build_source_health_admin_service()
    try:
        source_ids = service.list_probe_candidate_ids(limit=max(int(limit), 0))
        keywords = keyword_samples or list(SMART_SOURCE_HEALTH_KEYWORDS)
        if not source_ids:
            return {"results": [], "total": 0, "keyword_samples": keywords}
        result = await service.probe_book_sources(
            source_ids,
            keyword_samples=keywords,
            probe_mode=probe_mode,
        )
        return {**result, "keyword_samples": keywords, "source_ids": source_ids}
    finally:
        await _close_async_service(service)


async def _close_async_service(service) -> None:
    close = getattr(service, "aclose", None)
    if not callable(close):
        return
    result = close()
    if inspect.isawaitable(result):
        await result


async def run_catalog_source_discovery_job(limit: int = 50, origin_budget: int = 1) -> dict:
    from ..application.services.source_discovery_service import SourceDiscoveryService
    from ..infrastructure.persistence.factory import build_source_build_service, build_source_repository

    repo = build_source_repository()
    service = build_source_build_service()
    sources = await repo.list_book_sources_full(enabled_only=True)
    discovery = SourceDiscoveryService(origin_budget=max(origin_budget, 1))

    source_by_url: dict[str, dict] = {}
    for source in sources:
        url = str(source.get('bookSourceUrl') or '').strip()
        if not url:
            continue
        source_by_url[url] = source
        discovery.enqueue_candidate(url, priority=_catalog_source_discovery_priority(source))

    items: list[dict] = []
    selected_urls = discovery.next_jobs()[: max(limit, 0)]
    for url in selected_urls:
        source = source_by_url[url]
        submission = service.submit_catalog_discovery(
            tenant_id='system',
            url=url,
            catalog_source_id=source.get('id'),
            catalog_source_name=source.get('bookSourceName', ''),
            catalog_source_group=source.get('bookSourceGroup') or 'default',
        )
        items.append(
            {
                'catalog_source_id': source.get('id'),
                'catalog_source_name': source.get('bookSourceName', ''),
                'catalog_source_url': source.get('bookSourceUrl', ''),
                'job_id': submission.job_id,
                'source_version_id': submission.source_version_id,
                'status': submission.status,
            }
        )

    return {
        'total': len(items),
        'selected_urls': selected_urls,
        'items': items,
    }


def _catalog_source_discovery_priority(source: dict) -> int:
    status = str(source.get('sourceStatus') or '').strip().lower()
    error_message = str(source.get('errorMsg') or '').strip()
    last_check_time = source.get('lastCheckTime')
    group = str(source.get('bookSourceGroup') or '').strip().lower()

    priority = 0
    if status in {'error', 'failed', 'unhealthy', 'degraded'}:
        priority += 100
    elif status in {'unknown', '', 'pending'}:
        priority += 50
    elif status in {'warning', 'unstable'}:
        priority += 40
    elif status in {'ok', 'healthy'}:
        priority += 10

    if error_message:
        priority += 20
    if not last_check_time:
        priority += 15
    if group in {'seed', 'default', 'configured'}:
        priority += 5
    return priority


async def run_source_build_job(limit: int = 1) -> dict:
    from ..application.services.job_worker import JobWorker
    from ..infrastructure.persistence.factory import (
        build_job_service,
        build_source_build_audit_service,
        build_source_build_runtime_service,
    )

    service = build_job_service()
    runtime = build_source_build_runtime_service()
    audit_service = build_source_build_audit_service()
    outcomes: dict[str, dict] = {}

    def handler(job) -> None:
        build_result = runtime.handle_job(job)
        source_version_id = build_result.get('source_version_id') or job.payload.get('source_version_id')
        if not isinstance(source_version_id, str) or not source_version_id:
            raise ValueError('source.build job missing source version id for source audit')
        completed_repair_attempt = (
            job.payload.get('source_audit_attempt')
            if job.payload.get('trigger') == 'source_audit_repair'
            else None
        )
        outcomes[job.id] = {
            'build_result': build_result,
            'audit_result': audit_service.audit_blocking(
                source_version_id,
                completed_repair_attempt=completed_repair_attempt,
            ),
        }

    worker = JobWorker(
        service,
        worker_id='source-build-worker',
        handlers={'source.build': handler},
    )

    processed: list[dict] = []
    for _ in range(max(limit, 0)):
        result = await asyncio.to_thread(worker.run_once)
        if result is None:
            break
        processed.append(
            {
                'job_id': result.id,
                'status': result.status,
                'build_result': outcomes.get(result.id, {}).get('build_result'),
                'audit_result': outcomes.get(result.id, {}).get('audit_result'),
            }
        )

    return {
        'processed': len(processed),
        'jobs': processed,
    }


async def run_event_delivery_job(limit: int = 20) -> dict:
    service = build_event_delivery_service()
    deliveries = service.deliver_due_webhooks(limit=limit)
    return {
        'processed': len(deliveries),
        'deliveries': [
            {
                'event_id': delivery.event_id,
                'tenant_id': delivery.tenant_id,
                'status': delivery.status,
                'attempt_count': delivery.attempt_count,
            }
            for delivery in deliveries
        ],
    }
async def run_novel_index_job(limit: int = 10, owner_scope: str | None = None) -> dict:
    """Consume queued novel analysis tasks through the shared index service."""
    from ..infrastructure.persistence.factory import (
        build_novel_repository,
        build_novel_adaptive_learning_service,
        build_novel_runtime_repository,
        build_provider_platform_service,
        build_vector_store,
    )
    from ..application.services.novel_understanding.embedding import EmbeddingAdapter
    from ..application.services.novel_understanding.adjudicator import NovelAdjudicator
    from ..application.services.novel_understanding.index_service import NovelIndexService
    from .novel_index_worker import NovelIndexWorker

    repo = await build_novel_repository()
    platform = build_provider_platform_service()
    embedding = EmbeddingAdapter(provider=platform)
    index_service = NovelIndexService(
        repo,
        adaptive_learning=build_novel_adaptive_learning_service(repo),
        adjudicator=NovelAdjudicator(provider=platform, repo=repo),
        embedding=embedding,
        vector_store=build_vector_store(),
    )
    return await NovelIndexWorker(
        index_service=index_service,
        runtime_repo=build_novel_runtime_repository(),
        novel_repo=repo,
    ).run(limit=limit, owner_scope=owner_scope)
