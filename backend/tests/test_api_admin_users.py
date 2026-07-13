import asyncio

from fastapi.testclient import TestClient


def _setup_client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "admin-users.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.permissions import DEFAULT_ROLE_NAME
    from app.core.security import hash_password
    from app.domain.entities.auth import User
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = SQLiteAuthRepository()
    admin = asyncio.run(repo.save_user(User(username="admin", password_hash=hash_password("admin-password"))))
    asyncio.run(repo.assign_roles(admin.id, [DEFAULT_ROLE_NAME]))
    regular = asyncio.run(repo.save_user(User(username="reader", password_hash=hash_password("reader-password"))))
    asyncio.run(repo.assign_roles(regular.id, ["user"]))

    from app.main import app

    client = TestClient(app)
    admin_token = client.post("/api/auth/login", json={"username": "admin", "password": "admin-password"}).json()["data"]["access_token"]
    reader_token = client.post("/api/auth/login", json={"username": "reader", "password": "reader-password"}).json()["data"]["access_token"]
    return client, {"Authorization": f"Bearer {admin_token}"}, {"Authorization": f"Bearer {reader_token}"}, admin


def test_admin_can_create_user_without_exposing_password(monkeypatch, tmp_path):
    client, admin_headers, _, _ = _setup_client(monkeypatch, tmp_path)

    response = client.post("/api/admin/users", headers=admin_headers, json={
        "username": "new-reader", "display_name": "新读者", "role": "user", "password": "new-reader-password",
    })

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["role"] == "user"
    assert "password" not in str(data).lower()
    assert "hash" not in str(data).lower()


def test_regular_user_cannot_list_users(monkeypatch, tmp_path):
    client, _, reader_headers, _ = _setup_client(monkeypatch, tmp_path)
    response = client.get("/api/admin/users", headers=reader_headers)
    assert response.status_code == 403


def test_disabled_user_cannot_login_and_me_returns_roles(monkeypatch, tmp_path):
    client, admin_headers, _, _ = _setup_client(monkeypatch, tmp_path)
    created = client.post("/api/admin/users", headers=admin_headers, json={
        "username": "disabled", "display_name": "禁用读者", "role": "user", "password": "disabled-password",
    }).json()["data"]

    disabled = client.post(f"/api/admin/users/{created['id']}/disable", headers=admin_headers)
    assert disabled.status_code == 200
    login = client.post("/api/auth/login", json={"username": "disabled", "password": "disabled-password"})
    assert login.status_code == 401

    me = client.get("/api/auth/me", headers=admin_headers)
    assert me.status_code == 200
    assert "admin" in me.json()["data"]["roles"]


def test_cannot_disable_self_or_last_enabled_admin(monkeypatch, tmp_path):
    client, admin_headers, _, admin = _setup_client(monkeypatch, tmp_path)
    self_disable = client.post(f"/api/admin/users/{admin.id}/disable", headers=admin_headers)
    assert self_disable.status_code == 422


def test_revoke_user_sessions_requires_users_write_permission(monkeypatch, tmp_path):
    client, _, _, admin = _setup_client(monkeypatch, tmp_path)

    from app.core.security import create_access_token

    users_write_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(admin.id), 'permissions': ['users.write']})}"
    }
    jobs_manage_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(admin.id), 'permissions': ['system.jobs.manage']})}"
    }

    allowed = client.post(f"/api/admin/sessions/{admin.id}/revoke", headers=users_write_headers)
    denied = client.post(f"/api/admin/sessions/{admin.id}/revoke", headers=jobs_manage_headers)

    assert allowed.status_code == 200
    assert denied.status_code == 403
