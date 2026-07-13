from datetime import datetime, timedelta, timezone


async def test_auth_repo_can_create_admin_and_refresh_session(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "auth.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.permissions import DEFAULT_ROLE_NAME
    from app.core.security import hash_password
    from app.domain.entities.auth import RefreshSession, User
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = SQLiteAuthRepository()

    user = await repo.save_user(User(username="admin", password_hash=hash_password("admin123456")))
    await repo.assign_roles(user.id, [DEFAULT_ROLE_NAME])
    assert user.id > 0

    session = await repo.save_refresh_session(
        RefreshSession(
            id="sess-1",
            user_id=user.id,
            refresh_token_hash="abc",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
    )
    assert session.id == "sess-1"
    loaded = await repo.get_user_by_username("admin")
    assert loaded is not None
    assert loaded.username == "admin"
    assert "users.read" in loaded.permissions


async def test_auth_repository_updates_user_profile_role_and_active_state(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "auth.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.domain.entities.auth import User
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = SQLiteAuthRepository()
    user = await repo.save_user(User(username="reader", password_hash="hash"))

    updated = await repo.update_user(
        user.id,
        display_name="读者",
        is_active=False,
        role_names=["user"],
    )

    assert updated is not None
    assert updated.display_name == "读者"
    assert updated.is_active is False
    assert updated.role_names == ["user"]
