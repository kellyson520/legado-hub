def test_password_hash_is_not_plain_sha256(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import hash_password, verify_password

    hashed = hash_password("admin123456")
    assert hashed != "admin123456"
    assert hashed.startswith("$2")
    assert verify_password("admin123456", hashed) is True


def test_access_and_refresh_tokens_are_distinct(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token, create_refresh_token

    access = create_access_token({"sub": "1", "username": "admin"})
    refresh = create_refresh_token({"sub": "1", "session_id": "abc"})
    assert access != refresh
    assert isinstance(access, str)
    assert isinstance(refresh, str)
