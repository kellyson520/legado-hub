"""
中间件测试 — TraceMiddleware / RateLimitMiddleware

测试覆盖：
- TraceMiddleware：X-Trace-ID 注入和传播
- RateLimitMiddleware：限流触发和正常放行

测试策略：
- 直接实例化中间件，构造 ASGI scope 进行单元测试
- mock Redis 客户端，模拟限流判断
- 不连接真实 Redis/DB
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from app.core.middleware import AuditLogMiddleware, TraceMiddleware, RateLimitMiddleware


# ==================== TraceMiddleware 测试 ====================


def _make_mock_request(path: str, method: str = "GET", headers: dict = None) -> Request:
    """构造模拟的 Starlette Request 对象（完整 ASGI scope）"""
    # ASGI 规范要求 header name 必须为小写
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "client": ("192.168.1.1", 12345),
    }
    receive = AsyncMock(return_value={"type": "http.request", "body": b""})
    return Request(scope, receive)


@pytest.mark.asyncio
async def test_trace_middleware_generates_trace_id():
    """测试 TraceMiddleware — 请求无 X-Trace-ID 时自动生成并注入响应头"""
    call_next_called = False

    async def mock_call_next(request):
        nonlocal call_next_called
        call_next_called = True
        return Response(status_code=200, content=b"ok")

    middleware = TraceMiddleware(MagicMock())
    request = _make_mock_request("/api/v1/sources")

    with patch("app.core.middleware.set_log_context"), \
         patch("app.core.middleware.clear_log_context"):
        response = await middleware.dispatch(request, mock_call_next)

    assert call_next_called
    assert "X-Trace-ID" in response.headers
    assert len(response.headers["X-Trace-ID"]) == 16  # uuid4().hex[:16]


@pytest.mark.asyncio
async def test_trace_middleware_propagates_existing_trace_id():
    """测试 TraceMiddleware — 请求携带 X-Trace-ID 时直接传播，不生成新的"""
    trace_id = "my-custom-trace-1234"

    async def mock_call_next(request):
        return Response(status_code=200, content=b"ok")

    middleware = TraceMiddleware(MagicMock())
    request = _make_mock_request("/api/v1/sources", headers={"X-Trace-ID": trace_id})

    with patch("app.core.middleware.set_log_context") as mock_set, \
         patch("app.core.middleware.clear_log_context"):
        response = await middleware.dispatch(request, mock_call_next)

    # 验证 set_log_context 被调用时携带了传入的 trace_id
    mock_set.assert_called_once_with(trace_id=trace_id)
    assert response.headers["X-Trace-ID"] == trace_id


@pytest.mark.asyncio
async def test_trace_middleware_skips_static_paths():
    """测试 TraceMiddleware — 静态文件路径跳过 Trace 处理"""
    call_next_called = False

    async def mock_call_next(request):
        nonlocal call_next_called
        call_next_called = True
        resp = Response(status_code=200, content=b"static")
        # 静态文件路径不应注入 X-Trace-ID
        return resp

    middleware = TraceMiddleware(MagicMock())
    request = _make_mock_request("/static/js/app.js")

    response = await middleware.dispatch(request, mock_call_next)

    assert call_next_called
    # 静态路径跳过，不注入 X-Trace-ID
    assert "X-Trace-ID" not in response.headers


@pytest.mark.asyncio
async def test_trace_middleware_skips_health_paths():
    """测试 TraceMiddleware — 健康检查等路径跳过 Trace 处理"""
    async def mock_call_next(request):
        resp = Response(status_code=200, content=b"ok")
        return resp

    middleware = TraceMiddleware(MagicMock())

    # SKIP_PATHS 中的路径应跳过
    for path in ["/", "/api/status", "/docs", "/openapi.json", "/redoc", "/favicon.ico"]:
        request = _make_mock_request(path)
        response = await middleware.dispatch(request, mock_call_next)
        assert "X-Trace-ID" not in response.headers, f"路径 {path} 不应注入 X-Trace-ID"


@pytest.mark.asyncio
async def test_trace_middleware_handles_exception():
    """测试 TraceMiddleware — 请求处理异常时清理上下文并重新抛出"""
    async def mock_call_next(request):
        raise RuntimeError("模拟请求处理异常")

    middleware = TraceMiddleware(MagicMock())
    request = _make_mock_request("/api/v1/sources")

    with patch("app.core.middleware.set_log_context"), \
         patch("app.core.middleware.clear_log_context") as mock_clear:
        with pytest.raises(RuntimeError, match="模拟请求处理异常"):
            await middleware.dispatch(request, mock_call_next)

    # 确保异常时仍清理上下文
    mock_clear.assert_called_once()


@pytest.mark.asyncio
async def test_trace_middleware_records_identity_stored_on_request_state():
    async def mock_call_next(request):
        request.state.user_id = "42"
        request.state.api_key_id = 9
        return Response(status_code=200, content=b"ok")

    middleware = TraceMiddleware(MagicMock())
    request = _make_mock_request("/api/sources")

    with patch("app.core.middleware.logger.info") as info:
        await middleware.dispatch(request, mock_call_next)

    assert info.call_args.kwargs["extra"]["user_id"] == "42"
    assert info.call_args.kwargs["extra"]["api_key_id"] == 9


@pytest.mark.asyncio
async def test_audit_middleware_returns_before_background_audit_finishes():
    """审计写入不能增加用户请求的响应等待时间。"""
    started = asyncio.Event()
    release = asyncio.Event()

    async def mock_call_next(_request):
        return Response(status_code=201, content=b"created")

    async def delayed_audit(*_args):
        started.set()
        await release.wait()

    middleware = AuditLogMiddleware(MagicMock())
    middleware._record_audit = delayed_audit

    response = await middleware.dispatch(_make_mock_request("/api/sources", method="POST"), mock_call_next)

    assert response.status_code == 201
    assert response.background is not None
    background_task = asyncio.create_task(response.background())
    await asyncio.wait_for(started.wait(), timeout=0.1)
    release.set()
    await background_task


@pytest.mark.asyncio
async def test_audit_middleware_persists_the_authenticated_actor_from_request_state(monkeypatch):
    persisted = []

    def persist(event):
        persisted.append(event)

    monkeypatch.setattr(AuditLogMiddleware, "_persist_audit", staticmethod(persist), raising=False)
    middleware = AuditLogMiddleware(MagicMock())
    request = _make_mock_request("/api/sources", method="PATCH")
    request.state.user_id = "42"

    await middleware._record_audit(request, Response(status_code=200), 0.01)

    assert persisted[0].actor_id == 42
    assert persisted[0].action == "PATCH /api/sources"


# ==================== RateLimitMiddleware 测试 ====================


@pytest.mark.asyncio
async def test_rate_limit_middleware_passes_when_allowed():
    """测试 RateLimitMiddleware — 限流检查通过时正常放行并注入响应头"""
    async def mock_call_next(request):
        return Response(status_code=200, content=b"ok")

    middleware = RateLimitMiddleware(MagicMock(), default_limit=100, default_window=60)
    request = _make_mock_request("/api/v1/sources", headers={"X-Forwarded-For": "1.2.3.4"})

    # mock Redis 返回：allowed=True, remaining=95, reset_after=0
    with patch("app.core.middleware.redis_client") as mock_redis:
        mock_redis.check_rate_limit = AsyncMock(return_value=(True, 95, 0))
        response = await middleware.dispatch(request, mock_call_next)

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "100"
    assert response.headers["X-RateLimit-Remaining"] == "95"


@pytest.mark.asyncio
async def test_rate_limit_middleware_blocks_when_exceeded():
    """测试 RateLimitMiddleware — 超过限流阈值时返回 429 状态码"""
    async def mock_call_next(request):
        # 限流触发时不应调用 call_next
        return Response(status_code=200, content=b"ok")

    middleware = RateLimitMiddleware(MagicMock(), default_limit=10, default_window=60)
    request = _make_mock_request("/api/v1/sources")

    # mock Redis 返回：allowed=False, remaining=0, reset_after=30
    with patch("app.core.middleware.redis_client") as mock_redis:
        mock_redis.check_rate_limit = AsyncMock(return_value=(False, 0, 30))
        mock_redis.is_connected = True
        response = await middleware.dispatch(request, mock_call_next)

    assert response.status_code == 429
    data = response.body
    assert b"RATE_LIMIT_EXCEEDED" in data
    assert response.headers["X-RateLimit-Limit"] == "10"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["Retry-After"] == "30"


@pytest.mark.asyncio
async def test_rate_limit_middleware_skips_static_paths():
    """测试 RateLimitMiddleware — 静态文件路径跳过限流检查"""
    redis_called = False

    async def mock_call_next(request):
        return Response(status_code=200, content=b"static")

    def _set_redis_called():
        nonlocal redis_called
        redis_called = True
        return (True, 99, 0)

    middleware = RateLimitMiddleware(MagicMock(), default_limit=100, default_window=60)
    request = _make_mock_request("/static/css/style.css")

    with patch("app.core.middleware.redis_client") as mock_redis:
        mock_redis.check_rate_limit = AsyncMock(side_effect=_set_redis_called)
        response = await middleware.dispatch(request, mock_call_next)

    # 静态路径跳过限流，Redis 不应被调用
    assert not redis_called


@pytest.mark.asyncio
async def test_rate_limit_middleware_uses_ip_key_even_when_request_has_an_api_key_prefix():
    """认证前限流必须保持 IP 粒度，不能信任请求中的 Key 前缀。"""
    async def mock_call_next(request):
        return Response(status_code=200, content=b"ok")

    middleware = RateLimitMiddleware(MagicMock(), default_limit=100, default_window=60)
    request = _make_mock_request(
        "/api/v1/sources",
        headers={"Authorization": "Bearer lh_abcdefghijklmnop"},
    )

    with patch("app.core.middleware.redis_client") as mock_redis:
        mock_redis.check_rate_limit = AsyncMock(return_value=(True, 98, 0))

        await middleware.dispatch(request, mock_call_next)

        # 验证限流 key 仍使用客户端 IP
        call_args = mock_redis.check_rate_limit.call_args
        key = call_args[0][0]
        assert key == "ratelimit:ip:192.168.1.1"


@pytest.mark.asyncio
async def test_rate_limit_middleware_does_not_trust_rotating_unauthenticated_api_key_prefixes():
    async def mock_call_next(request):
        return Response(status_code=200, content=b"ok")

    middleware = RateLimitMiddleware(MagicMock(), default_limit=100, default_window=60)
    first = _make_mock_request("/api/v1/sources", headers={"Authorization": "Bearer lh_fake_one"})
    second = _make_mock_request("/api/v1/sources", headers={"Authorization": "Bearer lh_fake_two"})

    with patch("app.core.middleware.redis_client") as mock_redis:
        mock_redis.check_rate_limit = AsyncMock(return_value=(True, 99, 0))
        await middleware.dispatch(first, mock_call_next)
        await middleware.dispatch(second, mock_call_next)

    first_key = mock_redis.check_rate_limit.call_args_list[0].args[0]
    second_key = mock_redis.check_rate_limit.call_args_list[1].args[0]
    assert first_key == second_key == "ratelimit:ip:192.168.1.1"


@pytest.mark.asyncio
async def test_rate_limit_middleware_uses_ip_for_unauthenticated():
    """测试 RateLimitMiddleware — 无 API Key 时使用 IP 地址构建限流 key"""
    async def mock_call_next(request):
        return Response(status_code=200, content=b"ok")

    middleware = RateLimitMiddleware(MagicMock(), default_limit=100, default_window=60)
    request = _make_mock_request("/api/v1/sources")

    with patch("app.core.middleware.redis_client") as mock_redis:
        mock_redis.check_rate_limit = AsyncMock(return_value=(True, 99, 0))

        await middleware.dispatch(request, mock_call_next)

        call_args = mock_redis.check_rate_limit.call_args
        key = call_args[0][0]
        assert key.startswith("ratelimit:ip:192.168.1.1")
