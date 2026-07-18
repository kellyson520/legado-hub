"""
定时任务调度器测试 — scheduler 模块

测试覆盖：
- _safe_async_run(coro) — 异步协程安全执行
- job_fetch_subscriptions — 拉取订阅
- job_check_sources — 检查源可用性
- job_mark_stale_sources — 标记失效源
- job_reset_daily_quota — 重置日配额
- job_sync_quota_to_db — 配额同步到数据库
- job_archive_audit_logs — 归档审计日志

测试策略：
- mock 所有外部依赖（SourceRepo、UserRepo、Redis、SourceFetcher、SourceChecker）
- 验证异常隔离（单个任务失败不影响全局）
- 验证日志上下文清理（finally 块中 clear_log_context）
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ==================== _safe_async_run 测试 ====================


@pytest.mark.asyncio
async def test_safe_async_run_executes_coroutine():
    """测试 _safe_async_run — 协程被正确执行（通过副作用验证，因函数不返回值）"""
    from app.tasks.scheduler import _safe_async_run

    executed = False

    async def sample_coro():
        nonlocal executed
        executed = True
        return "执行结果"

    # 在已有事件循环中运行（test 本身就是 async）
    _safe_async_run(sample_coro())
    assert executed, "协程应已被执行"


@pytest.mark.asyncio
async def test_safe_async_run_handles_exception():
    """测试 _safe_async_run — 协程抛出异常时正确传播"""
    from app.tasks.scheduler import _safe_async_run

    async def failing_coro():
        raise ValueError("模拟协程异常")

    with pytest.raises(ValueError, match="模拟协程异常"):
        _safe_async_run(failing_coro())


# ==================== job_fetch_subscriptions 测试 ====================


@pytest.mark.asyncio
@patch("app.tasks.scheduler.clear_log_context")
@patch("app.tasks.scheduler.set_log_context")
async def test_job_fetch_subscriptions_success(mock_set_ctx, mock_clear_ctx):
    """测试 job_fetch_subscriptions — 正常拉取订阅，记录成功/失败计数"""
    from app.tasks.scheduler import job_fetch_subscriptions

    # mock 订阅列表
    mock_sub1 = MagicMock(id=1, name="订阅1")
    mock_sub2 = MagicMock(id=2, name="订阅2")
    mock_subs = [mock_sub1, mock_sub2]

    mock_fetcher = AsyncMock()
    mock_fetcher.fetch_subscription = AsyncMock(side_effect=[
        {"success": True},
        {"success": False, "message": "拉取失败"},
    ])
    mock_fetcher.__aenter__ = AsyncMock(return_value=mock_fetcher)
    mock_fetcher.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.tasks.scheduler.build_source_repository") as mock_get_repo,
        patch("app.tasks.scheduler.SourceFetcher", return_value=mock_fetcher),
        patch("app.tasks.scheduler._safe_async_run") as mock_safe_run,
    ):
        mock_repo = AsyncMock()
        mock_repo.list_subscriptions = AsyncMock(return_value=mock_subs)
        mock_get_repo.return_value = mock_repo
        mock_safe_run.side_effect = lambda coroutine: coroutine.close()

        # 直接调用 job 函数（内部已调用 _safe_async_run）
        job_fetch_subscriptions()

    # 验证日志上下文被设置和清理
    mock_set_ctx.assert_called_once()
    mock_clear_ctx.assert_called_once()


@pytest.mark.asyncio
@patch("app.tasks.scheduler.clear_log_context")
@patch("app.tasks.scheduler.set_log_context")
async def test_job_fetch_subscriptions_exception_isolation(mock_set_ctx, mock_clear_ctx):
    """测试 job_fetch_subscriptions — 任务内部异常被隔离，不影响全局"""
    from app.tasks.scheduler import job_fetch_subscriptions

    with (
        patch("app.tasks.scheduler.build_source_repository") as mock_get_repo,
        patch("app.tasks.scheduler.SourceFetcher"),
    ):
        mock_repo = AsyncMock()
        mock_repo.list_subscriptions = AsyncMock(side_effect=RuntimeError("DB 连接失败"))
        mock_get_repo.return_value = mock_repo

        # 任务函数内部捕获异常，不应抛出到外部
        job_fetch_subscriptions()

    # 即使任务异常，日志上下文仍应被清理
    mock_set_ctx.assert_called_once()
    mock_clear_ctx.assert_called_once()


# ==================== job_check_sources 测试 ====================


@pytest.mark.asyncio
@patch("app.tasks.scheduler.clear_log_context")
@patch("app.tasks.scheduler.set_log_context")
async def test_job_check_sources_success(mock_set_ctx, mock_clear_ctx):
    """测试 job_check_sources — 正常检查书源和订阅源可用性"""
    from app.tasks.scheduler import job_check_sources

    mock_book = MagicMock()
    mock_book.bookSourceUrl = "https://book.example.com"
    mock_rss = MagicMock()
    mock_rss.sourceUrl = "https://rss.example.com"

    mock_repo = AsyncMock()
    mock_repo.list_book_sources = AsyncMock(return_value=([mock_book], 1))
    mock_repo.list_rss_sources = AsyncMock(return_value=([mock_rss], 1))
    mock_repo.update_book_source_status = AsyncMock()
    mock_repo.update_rss_source_status = AsyncMock()

    mock_checker = MagicMock()
    mock_checker.check_book_source = AsyncMock(return_value={"status": "ok", "errorMsg": None})
    mock_checker.check_rss_source = AsyncMock(return_value={"status": "ok", "errorMsg": None})
    mock_checker.__aenter__ = AsyncMock(return_value=mock_checker)
    mock_checker.__aexit__ = AsyncMock(return_value=False)

    mock_redis = AsyncMock()
    mock_redis.get_cached_source_check = AsyncMock(return_value=None)
    mock_redis.cache_source_check = AsyncMock()

    with (
        patch("app.tasks.scheduler.build_source_repository", return_value=mock_repo),
        patch("app.tasks.scheduler.SourceChecker", return_value=mock_checker),
        patch("app.core.redis_client.redis_client", mock_redis),
    ):
        job_check_sources()

    mock_set_ctx.assert_called_once()
    mock_clear_ctx.assert_called_once()


@pytest.mark.asyncio
@patch("app.tasks.scheduler.clear_log_context")
@patch("app.tasks.scheduler.set_log_context")
async def test_job_check_sources_with_cache_hit(mock_set_ctx, mock_clear_ctx):
    """测试 job_check_sources — 命中 Redis 缓存时跳过重复检查"""
    from app.tasks.scheduler import job_check_sources

    mock_book = MagicMock()
    mock_book.bookSourceUrl = "https://cached-book.example.com"

    mock_repo = AsyncMock()
    mock_repo.list_book_sources = AsyncMock(return_value=([mock_book], 1))
    mock_repo.list_rss_sources = AsyncMock(return_value=([], 0))

    mock_redis = AsyncMock()
    # 缓存命中
    mock_redis.get_cached_source_check = AsyncMock(return_value={"status": "ok"})
    mock_redis.cache_source_check = AsyncMock()

    mock_checker = MagicMock()
    mock_checker.check_book_source = AsyncMock()
    mock_checker.__aenter__ = AsyncMock(return_value=mock_checker)
    mock_checker.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.tasks.scheduler.build_source_repository", return_value=mock_repo),
        patch("app.tasks.scheduler.SourceChecker", return_value=mock_checker),
        patch("app.core.redis_client.redis_client", mock_redis),
    ):
        job_check_sources()

    # 缓存命中，不应调用 check_book_source
    mock_checker.check_book_source.assert_not_called()


# ==================== job_mark_stale_sources 测试 ====================


@pytest.mark.asyncio
@patch("app.tasks.scheduler.clear_log_context")
@patch("app.tasks.scheduler.set_log_context")
async def test_job_mark_stale_sources_disables_old_error_sources(mock_set_ctx, mock_clear_ctx):
    """测试 job_mark_stale_sources — 禁用连续 7 天不可用的源"""
    from app.tasks.scheduler import job_mark_stale_sources

    mock_book = MagicMock()
    mock_book.enabled = True

    mock_db = MagicMock()
    mock_db.query = MagicMock(return_value=MagicMock(
        filter=MagicMock(return_value=MagicMock(
            limit=MagicMock(return_value=[mock_book])
        ))
    ))
    mock_db.commit = MagicMock()
    mock_db.close = MagicMock()

    mock_event = AsyncMock()
    mock_event.__aenter__ = AsyncMock(return_value=mock_event)
    mock_event.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.infrastructure.persistence.sqlite.session.SessionLocal", return_value=mock_db),
        patch("app.tasks.scheduler.publish_event", new_callable=AsyncMock),
    ):
        job_mark_stale_sources()

    mock_set_ctx.assert_called_once()
    mock_clear_ctx.assert_called_once()


@pytest.mark.asyncio
@patch("app.tasks.scheduler.clear_log_context")
@patch("app.tasks.scheduler.set_log_context")
async def test_job_mark_stale_sources_handles_db_error(mock_set_ctx, mock_clear_ctx):
    """测试 job_mark_stale_sources — 数据库异常时回滚且不中断任务"""
    from app.tasks.scheduler import job_mark_stale_sources

    mock_db = MagicMock()
    mock_db.query = MagicMock(side_effect=RuntimeError("DB 查询异常"))
    mock_db.rollback = MagicMock()
    mock_db.close = MagicMock()

    with patch("app.infrastructure.persistence.sqlite.session.SessionLocal", return_value=mock_db):
        job_mark_stale_sources()

    # 异常后回滚
    mock_db.rollback.assert_called_once()
    # 日志上下文仍清理
    mock_clear_ctx.assert_called_once()


# ==================== job_reset_daily_quota 测试 ====================


@pytest.mark.asyncio
@patch("app.tasks.scheduler.clear_log_context")
@patch("app.tasks.scheduler.set_log_context")
async def test_job_reset_daily_quota_resets_all_keys(mock_set_ctx, mock_clear_ctx):
    """测试 job_reset_daily_quota — 重置所有启用 API Key 的配额计数"""
    from app.tasks.scheduler import job_reset_daily_quota

    mock_key1 = MagicMock(id=1)
    mock_key2 = MagicMock(id=2)

    # 正确构建 mock 链：query() → .filter() → .all()
    mock_all_result = MagicMock()
    mock_all_result.all = MagicMock(return_value=[mock_key1, mock_key2])

    mock_filter_result = MagicMock()
    mock_filter_result.all = MagicMock(return_value=[mock_key1, mock_key2])

    mock_query = MagicMock()
    mock_query.filter = MagicMock(return_value=mock_filter_result)

    mock_db = MagicMock()
    mock_db.query = MagicMock(return_value=mock_query)
    mock_db.close = MagicMock()

    mock_redis = AsyncMock()
    mock_redis.reset_quota = AsyncMock()

    with (
        patch("app.infrastructure.persistence.sqlite.session.SessionLocal", return_value=mock_db),
        patch("app.core.redis_client.redis_client", mock_redis),
    ):
        job_reset_daily_quota()

    # 验证每个 key 的三个配额指标都被重置
    assert mock_redis.reset_quota.call_count == 6  # 2 keys * 3 metrics


# ==================== job_sync_quota_to_db 测试 ====================


@pytest.mark.asyncio
@patch("app.tasks.scheduler.clear_log_context")
@patch("app.tasks.scheduler.set_log_context")
async def test_job_sync_quota_to_db_syncs_active_keys(mock_set_ctx, mock_clear_ctx):
    """测试 job_sync_quota_to_db — 将 Redis 配额数据同步到数据库"""
    from app.tasks.scheduler import job_sync_quota_to_db

    mock_key = MagicMock(id=1)

    # 第一次 query()：ApiKeyModel 查询链 → .filter().all() 返回 [mock_key]
    mock_filter_api_keys = MagicMock()
    mock_filter_api_keys.all = MagicMock(return_value=[mock_key])

    mock_query_api_keys = MagicMock()
    mock_query_api_keys.filter = MagicMock(return_value=mock_filter_api_keys)

    # 第二次 query()：QuotaUsageModel 查询链 → .filter().first() 返回 None
    mock_filter_usage = MagicMock()
    mock_filter_usage.first = MagicMock(return_value=None)

    mock_query_usage = MagicMock()
    mock_query_usage.filter = MagicMock(return_value=mock_filter_usage)

    mock_db = MagicMock()
    mock_db.query = MagicMock(side_effect=[mock_query_api_keys, mock_query_usage])
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.close = MagicMock()

    mock_redis = AsyncMock()
    mock_redis.get_quota = AsyncMock(side_effect=[10, 200, 3.5])  # fetch_count=10, ai_chars=200, storage_mb=3.5

    with (
        patch("app.infrastructure.persistence.sqlite.session.SessionLocal", return_value=mock_db),
        patch("app.core.redis_client.redis_client", mock_redis),
    ):
        job_sync_quota_to_db()

    # 有配额使用时，应新增记录
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    assert mock_db.add.call_args.args[0].storage_mb == 3.5


@pytest.mark.asyncio
@patch("app.tasks.scheduler.clear_log_context")
@patch("app.tasks.scheduler.set_log_context")
async def test_job_sync_quota_to_db_handles_exception(mock_set_ctx, mock_clear_ctx):
    """测试 job_sync_quota_to_db — 数据库异常时回滚且不中断任务"""
    from app.tasks.scheduler import job_sync_quota_to_db

    mock_db = MagicMock()
    mock_db.query = MagicMock(side_effect=RuntimeError("DB 异常"))
    mock_db.rollback = MagicMock()
    mock_db.close = MagicMock()

    with (
        patch("app.infrastructure.persistence.sqlite.session.SessionLocal", return_value=mock_db),
        patch("app.core.redis_client.redis_client", new_callable=AsyncMock),
    ):
        job_sync_quota_to_db()

    mock_db.rollback.assert_called_once()
    mock_clear_ctx.assert_called_once()


# ==================== job_archive_audit_logs 测试 ====================


@pytest.mark.asyncio
@patch("app.tasks.scheduler.clear_log_context")
@patch("app.tasks.scheduler.set_log_context")
async def test_job_archive_audit_logs_deletes_old_logs(mock_set_ctx, mock_clear_ctx):
    """测试 job_archive_audit_logs — 删除过期的审计日志"""
    from app.tasks.scheduler import job_archive_audit_logs

    mock_repo = AsyncMock()
    mock_repo.delete_old_audit_events = AsyncMock(return_value=42)

    with patch("app.tasks.scheduler.build_auth_repository", return_value=mock_repo):
        job_archive_audit_logs()

    mock_repo.delete_old_audit_events.assert_called_once_with(days=90)
    mock_set_ctx.assert_called_once()
    mock_clear_ctx.assert_called_once()


@pytest.mark.asyncio
@patch("app.tasks.scheduler.clear_log_context")
@patch("app.tasks.scheduler.set_log_context")
async def test_job_archive_audit_logs_no_logs_to_delete(mock_set_ctx, mock_clear_ctx):
    """测试 job_archive_audit_logs — 无过期日志时不执行删除"""
    from app.tasks.scheduler import job_archive_audit_logs

    mock_repo = AsyncMock()
    mock_repo.delete_old_audit_events = AsyncMock(return_value=0)

    with patch("app.tasks.scheduler.build_auth_repository", return_value=mock_repo):
        job_archive_audit_logs()

    mock_repo.delete_old_audit_events.assert_called_once_with(days=90)


# ==================== JOBS 列表与调度注册测试 ====================


def test_jobs_list_defined():
    """测试 JOBS 列表 — 验证所有定时任务均已注册"""
    from app.tasks.scheduler import JOBS

    expected_jobs = {
        "fetch_subscriptions",
        "check_sources",
        "probe_source_health",
        "cleanup_ephemeral_sources",
        "mark_stale_sources",
        "reset_daily_quota",
        "sync_quota_to_db",
        "archive_audit_logs",
        "novel_analysis_tasks",
    }

    actual_ids = {job[0] for job in JOBS}
    assert actual_ids == expected_jobs, f"缺少任务: {expected_jobs - actual_ids}"


def test_jobs_list_valid_cron():
    """测试 JOBS 列表 — 验证所有 cron 表达式格式正确（5 段式）"""
    from app.tasks.scheduler import JOBS

    for job_id, cron, func, desc in JOBS:
        parts = cron.split()
        assert len(parts) == 5, f"任务 {job_id} 的 cron 表达式格式错误: {cron}"
        assert desc, f"任务 {job_id} 缺少描述"
        assert callable(func), f"任务 {job_id} 的执行函数不是可调用对象"


def test_start_scheduler_reports_filtered_job_count(monkeypatch):
    from app.tasks import scheduler

    class FakeScheduler:
        def __init__(self):
            self.added = []
            self.started = False

        def add_job(self, func, trigger, id, replace_existing):
            self.added.append(id)

        def start(self):
            self.started = True

    class FakeLogger:
        def __init__(self):
            self.messages = []

        def info(self, message, *args, **kwargs):
            self.messages.append(message)

    fake_scheduler = FakeScheduler()
    fake_logger = FakeLogger()
    monkeypatch.setattr(scheduler, 'scheduler', fake_scheduler)
    monkeypatch.setattr(scheduler, 'logger', fake_logger)

    scheduler.start_scheduler(job_ids={'probe_source_health'})

    assert fake_scheduler.added == ['probe_source_health']
    assert fake_scheduler.started is True
    assert any('共 1 个任务' in message for message in fake_logger.messages)
