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

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from app.core.middleware import TraceMiddleware, RateLimitMiddleware


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
async def test_rate_limit_middleware_does_not_trust_unverified_api_key_prefix():
    """未经过认证的 API Key 外观值必须仍按客户端 IP 限流。"""
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

        # 认证依赖在路由阶段才会验证 API Key；中间件不得把任意 lh_ 值
        # 当成独立限流主体，否则攻击者可不断更换伪造值绕过 IP 限流。
        call_args = mock_redis.check_rate_limit.call_args
        key = call_args[0][0]
        assert key == "ratelimit:ip:192.168.1.1"


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
