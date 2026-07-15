"""Application startup must activate the shared observability stack."""


def test_application_registers_trace_rate_limit_and_audit_middleware():
    from app.core.middleware import AuditLogMiddleware, RateLimitMiddleware, TraceMiddleware
    from app.main import app

    middleware_classes = {item.cls for item in app.user_middleware}

    assert TraceMiddleware in middleware_classes
    assert RateLimitMiddleware in middleware_classes
    assert AuditLogMiddleware in middleware_classes
