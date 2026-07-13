"""
定时任务调度器

职责：
- 异步执行定时任务（不再使用 asyncio.run 反模式）
- 统一日志（每个任务独立 trace）
- 异常隔离（单个任务失败不影响其他任务）
- 发布领域事件
"""

import asyncio
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..core.logging import get_logger, set_log_context, clear_log_context
from ..core.events import publish_event, SourceFetchedEvent, SystemNoticeEvent
from ..infrastructure.persistence.factory import get_source_repo, get_user_repo
from ..services.fetcher import SourceFetcher, SourceChecker

logger = get_logger("scheduler")
scheduler = BackgroundScheduler()


def _safe_async_run(coro):
    """安全执行异步协程（用于 APScheduler 同步上下文中调用异步代码）"""
    try:
        loop = asyncio.get_running_loop()
        # 已有事件循环，用 nest
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            future.result(timeout=300)
    except RuntimeError:
        asyncio.run(coro)


def job_fetch_subscriptions():
    """定时拉取所有订阅"""
    job_name = "fetch_subscriptions"
    set_log_context(trace_id=f"job_{datetime.utcnow().timestamp():.0f}")
    logger.info(f"[定时任务] 开始拉取订阅", extra={"action": "job_start", "job": job_name})

    async def _do():
        subs = (await get_source_repo().list_subscriptions(enabled_only=True))
        logger.info(f"[定时任务] 共 {len(subs)} 个活跃订阅", extra={"action": job_name, "count": len(subs)})

        success_count = 0
        fail_count = 0
        async with SourceFetcher() as fetcher:
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

        repo = get_source_repo()
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


def job_mark_stale_sources():
    """标记长期失效的源"""
    job_name = "mark_stale_sources"
    set_log_context(trace_id=f"job_{datetime.utcnow().timestamp():.0f}")
    logger.info(f"[定时任务] 开始清理失效源", extra={"action": "job_start", "job": job_name})

    async def _do():
        repo = get_source_repo()
        from datetime import datetime
        stale_threshold = datetime.utcnow() - timedelta(days=7)

        # 使用底层 DB 直接更新（避免领域层逻辑干扰清理任务）
        from ..database import SessionLocal, BookSourceModel, RssSourceModel
        db = SessionLocal()
        try:
            disabled_books = db.query(BookSourceModel).filter(
                BookSourceModel.sourceStatus == "error",
                BookSourceModel.lastCheckTime < stale_threshold,
                BookSourceModel.enabled == True
            ).limit(100).all()

            for s in disabled_books:
                s.enabled = False
                logger.info(f"[定时任务] 禁用失效书源: {s.bookSourceName}", extra={"action": job_name, "source_url": s.bookSourceUrl})

            disabled_rss = db.query(RssSourceModel).filter(
                RssSourceModel.sourceStatus == "error",
                RssSourceModel.lastCheckTime < stale_threshold,
                RssSourceModel.enabled == True
            ).limit(100).all()

            for s in disabled_rss:
                s.enabled = False
                logger.info(f"[定时任务] 禁用失效订阅源: {s.sourceName}", extra={"action": job_name, "source_url": s.sourceUrl})

            db.commit()
            total = len(disabled_books) + len(disabled_rss)
            if total > 0:
                logger.info(f"[定时任务] 自动禁用 {total} 个失效源", extra={"action": "job_end", "job": job_name, "disabled": total})
                await publish_event(SystemNoticeEvent(
                    level="warning",
                    title="失效源清理",
                    content=f"已自动禁用 {total} 个连续 7 天不可用的源"
                ))
        except Exception as e:
            db.rollback()
            logger.error(f"[定时任务] 失效源清理异常: {e}", extra={"action": "job_error", "job": job_name, "error": str(e)}, exc_info=True)
        finally:
            db.close()

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
        from ..core.redis_client import redis_client
        from ..database import SessionLocal, ApiKeyModel
        db = SessionLocal()
        try:
            keys = db.query(ApiKeyModel).filter(ApiKeyModel.is_enabled == True).all()
            for key in keys:
                await redis_client.reset_quota(key.id, "fetch_count")
                await redis_client.reset_quota(key.id, "ai_chars")
                await redis_client.reset_quota(key.id, "storage_mb")
            logger.info(f"[定时任务] 已重置 {len(keys)} 个 API Key 配额", extra={"action": "job_end", "job": job_name, "count": len(keys)})
        except Exception as e:
            logger.error(f"[定时任务] 配额重置异常: {e}", extra={"action": "job_error", "job": job_name, "error": str(e)}, exc_info=True)
        finally:
            db.close()

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
        from ..core.redis_client import redis_client
        from ..database import SessionLocal, ApiKeyModel, QuotaUsageModel
        db = SessionLocal()
        try:
            keys = db.query(ApiKeyModel).filter(ApiKeyModel.is_enabled == True).all()
            today = datetime.utcnow().strftime("%Y-%m-%d")
            synced = 0
            for key in keys:
                fetch_count = await redis_client.get_quota(key.id, "fetch_count")
                ai_chars = await redis_client.get_quota(key.id, "ai_chars")
                if fetch_count > 0 or ai_chars > 0:
                    usage = db.query(QuotaUsageModel).filter(
                        QuotaUsageModel.api_key_id == key.id,
                        QuotaUsageModel.date == today
                    ).first()
                    if not usage:
                        usage = QuotaUsageModel(api_key_id=key.id, date=today, fetch_count=fetch_count, ai_chars=ai_chars)
                        db.add(usage)
                    else:
                        usage.fetch_count = max(usage.fetch_count or 0, fetch_count)
                        usage.ai_chars = max(usage.ai_chars or 0, ai_chars)
                    synced += 1
            db.commit()
            if synced > 0:
                logger.info(f"[定时任务] 配额同步: {synced} 个 key", extra={"action": job_name, "synced": synced})
        except Exception as e:
            db.rollback()
            logger.error(f"[定时任务] 配额同步异常: {e}", extra={"action": "job_error", "job": job_name, "error": str(e)}, exc_info=True)
        finally:
            db.close()

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
        repo = get_user_repo()
        deleted = await repo.archive_old_logs(days=90)
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


# ==================== 调度注册 ====================

JOBS = [
    ("fetch_subscriptions", "0 */2 * * *", job_fetch_subscriptions, "每2小时拉取订阅"),
    ("check_sources", "0 */4 * * *", job_check_sources, "每4小时检查可用性"),
    ("mark_stale_sources", "0 3 * * *", job_mark_stale_sources, "每天3点清理失效源"),
    ("reset_daily_quota", "0 0 * * *", job_reset_daily_quota, "每天0点重置配额"),
    ("sync_quota_to_db", "*/30 * * * *", job_sync_quota_to_db, "每30分钟同步配额"),
    ("archive_audit_logs", "0 2 * * 0", job_archive_audit_logs, "每周日2点归档日志"),
]


def start_scheduler():
    """启动调度器"""
    for job_id, cron, func, desc in JOBS:
        scheduler.add_job(func, CronTrigger.from_crontab(cron), id=job_id, replace_existing=True)
        logger.info(f"[调度器] 注册任务: {job_id} ({cron}) - {desc}")

    scheduler.start()
    logger.info(f"[调度器] 启动完成, 共 {len(JOBS)} 个任务")


def stop_scheduler():
    scheduler.shutdown()
    logger.info("[调度器] 已停止")


async def run_source_runtime_health_job() -> list[dict]:
    from ..infrastructure.persistence.factory import build_source_health_service

    service = build_source_health_service()
    return await service.verify_published_versions()

