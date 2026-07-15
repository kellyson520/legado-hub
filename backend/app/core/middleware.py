"""
请求中间件 — 限流 / 审计 / Trace 传播

职责：
- 滑动窗口限流（Redis / 内存降级）
- 审计日志（写操作记录到 DB）
- Trace ID 生成与传播
- 统一日志（禁止缺失日志）
- 统一异常（RateLimitException）

关键约束（禁止缺失日志）：
- 限流拦截 → WARNING + 结构化信息
- 审计记录成功/失败 → 各有日志
- Trace ID 生成 → 注入到日志上下文
"""

import json
import time
import uuid
import asyncio
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

from .logging import get_logger, set_log_context, clear_log_context
from .redis_client import redis_client
from .config import settings

logger = get_logger("middleware")


class TraceMiddleware(BaseHTTPMiddleware):
    """
    Trace ID 传播中间件

    职责：
    - 从请求头提取 X-Trace-ID（如果存在）
    - 不存在则生成新的 Trace ID
    - 注入到线程本地存储（供统一日志使用）
    - 请求结束后清理上下文
    """

    SKIP_PATHS = {"/", "/api/status", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 静态文件和健康检查跳过
        if path.startswith("/static") or path in self.SKIP_PATHS:
            return await call_next(request)

        # 生成/提取 Trace ID
        trace_id = request.headers.get("X-Trace-ID") or uuid.uuid4().hex[:16]
        set_log_context(trace_id=trace_id)

        # 注入响应头（方便客户端关联）
        start_time = time.time()

        try:
            response = await call_next(request)
            response.headers["X-Trace-ID"] = trace_id

            elapsed = (time.time() - start_time) * 1000
            logger.info(
                f"[Trace] {request.method} {path} → {response.status_code} ({elapsed:.0f}ms)",
                extra={
                    "action": "request_done",
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": round(elapsed, 2),
                    "user_id": getattr(request.state, "user_id", None),
                    "api_key_id": getattr(request.state, "api_key_id", None),
                }
            )
            return response
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(
                f"[Trace] 请求异常: {request.method} {path} - {type(e).__name__}: {e}",
                extra={
                    "action": "request_error",
                    "method": request.method,
                    "path": path,
                    "error": str(e),
                    "duration_ms": round(elapsed, 2),
                },
                exc_info=True
            )
            raise
        finally:
            clear_log_context()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    API 限流中间件 — 基于 Redis 滑动窗口

    日志覆盖：
    - 限流触发 → WARNING（携带 IP/Key 前缀）
    - Redis 降级 → WARNING
    - 请求通过 → DEBUG（携带剩余次数）
    """

    SKIP_PATHS = {"/", "/api/status", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, app, default_limit: int = None, default_window: int = 60):
        super().__init__(app)
        self.default_limit = default_limit or settings.RATE_LIMIT_PER_MINUTE
        self.default_window = default_window

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 跳过静态文件和文档
        if path.startswith("/static") or path in self.SKIP_PATHS:
            return await call_next(request)

        # 构建限流 key
        client_ip = request.client.host if request.client else "unknown"
        # Authentication is resolved deeper in the request stack. Never trust an
        # unauthenticated token prefix here, otherwise rotating fake keys bypass
        # the shared pre-auth IP window.
        key = f"ratelimit:ip:{client_ip}"

        # 检查限流
        allowed, remaining, reset_after = await redis_client.check_rate_limit(
            key, self.default_limit, self.default_window
        )

        if not allowed:
            logger.warning(
                f"[RateLimit] 限流触发: key={key}, client={client_ip}, path={path}, reset={reset_after}s",
                extra={
                    "action": "rate_limit_triggered",
                    "key": key,
                    "client_ip": client_ip,
                    "path": path,
                    "reset_after": reset_after,
                }
            )

            # 检查 Redis 是否降级（未连接时 remaining == max_requests）
            if not redis_client.is_connected:
                logger.warning(
                    "[RateLimit] Redis 未连接，限流降级为无限制",
                    extra={"action": "rate_limit_degraded"}
                )

            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit exceeded. Try again in {reset_after}s.",
                },
                headers={
                    "X-RateLimit-Limit": str(self.default_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_after),
                    "Retry-After": str(reset_after),
                }
            )

        # 继续处理请求
        start_time = time.time()
        response = await call_next(request)
        elapsed = time.time() - start_time

        # 添加限流响应头
        response.headers["X-RateLimit-Limit"] = str(self.default_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-Process-Time"] = f"{elapsed:.3f}"

        return response


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    审计日志中间件 — 记录关键写操作

    日志覆盖：
    - 审计记录成功 → INFO
    - 审计记录失败 → WARNING（不阻断请求）
    - 使用仓储接口（DDD 解耦）
    """

    WRITABLE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
    SKIP_PATHS = {"/static", "/docs", "/openapi.json"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        # 只记录写操作
        if method not in self.WRITABLE_METHODS or any(path.startswith(p) for p in self.SKIP_PATHS):
            return await call_next(request)

        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time

        # SQLite 审计仓储是同步 I/O；将持久化放到响应路径之外。
        task = asyncio.create_task(self._record_audit(request, response, duration))
        task.add_done_callback(self._report_audit_task_failure)

        return response

    @staticmethod
    def _report_audit_task_failure(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        try:
            error = task.exception()
        except asyncio.CancelledError:
            return
        if error is not None:
            logger.warning(
                f"[Audit] 审计记录异常: {type(error).__name__}: {error}",
                extra={"action": "audit_error", "error": str(error)},
                exc_info=(type(error), error, error.__traceback__),
            )

    async def _record_audit(self, request: Request, response: Response, duration: float):
        """Persist a compact audit event through the active auth repository contract."""
        from ..domain.entities.auth import AuditEvent

        client_ip = request.client.host if request.client else "unknown"
        raw_user_id = getattr(request.state, "user_id", None)
        try:
            actor_id = int(raw_user_id) if raw_user_id is not None else None
        except (TypeError, ValueError):
            actor_id = None
        api_key_id = getattr(request.state, "api_key_id", None)
        audit = AuditEvent(
            actor_id=actor_id,
            action=f"{request.method} {request.url.path}",
            resource="api",
            detail=json.dumps({
                "method": request.method,
                "path": str(request.url.path),
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
                "client_ip": client_ip,
                "user_agent": request.headers.get("User-Agent", "")[:200],
                "api_key_id": api_key_id,
            }, ensure_ascii=False, separators=(",", ":")),
        )

        await asyncio.to_thread(self._persist_audit, audit)
        logger.info(
            f"[Audit] 审计记录: {request.method} {request.url.path} → {response.status_code} ({duration * 1000:.0f}ms)",
            extra={
                "action": "audit_recorded",
                "method": request.method,
                "path": str(request.url.path),
                "status_code": response.status_code,
                "api_key_id": api_key_id,
                "user_id": actor_id,
                "duration_ms": round(duration * 1000, 2),
            }
        )

    @staticmethod
    def _persist_audit(event) -> None:
        from ..infrastructure.persistence.factory import build_auth_repository

        asyncio.run(build_auth_repository().record_audit(event))
