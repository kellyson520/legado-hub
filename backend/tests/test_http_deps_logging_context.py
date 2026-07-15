"""HTTP authentication must enrich the current request log context."""


def test_jwt_identity_adds_user_id_to_log_context():
    from app.core.logging import _context, clear_log_context
    from app.core.security import create_access_token
    from app.interfaces.http.deps import get_current_identity
    from starlette.requests import Request

    clear_log_context()
    token = create_access_token({"sub": "42", "permissions": ["book_sources.read"]})

    request = Request({"type": "http", "headers": []})
    identity = get_current_identity(request=request, authorization=f"Bearer {token}")

    assert identity.user_id == 42
    assert _context.user_id == "42"
    assert request.state.user_id == "42"
    clear_log_context()
