import asyncio

from fastapi.testclient import TestClient


def test_login_refresh_logout_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "auth-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.permissions import DEFAULT_ROLE_NAME
    from app.core.security import hash_password
    from app.domain.entities.auth import User
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = SQLiteAuthRepository()
    user = asyncio.run(repo.save_user(User(username="admin", password_hash=hash_password("admin123456"))))
    asyncio.run(repo.assign_roles(user.id, [DEFAULT_ROLE_NAME]))

    from app.main import app

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
    assert login.status_code == 200
    payload = login.json()["data"]
    assert payload["access_token"]
    assert payload["refresh_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert me.status_code == 200
    assert me.json()["data"]["user_id"] > 0

    refresh = client.post("/api/auth/refresh", json={"refresh_token": payload["refresh_token"]})
    assert refresh.status_code == 200
    assert refresh.json()["data"]["access_token"]

    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert logout.status_code == 200


def test_logout_all_revokes_current_user_sessions(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "auth-api-logout-all.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.permissions import DEFAULT_ROLE_NAME
    from app.core.security import hash_password
    from app.domain.entities.auth import User
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = SQLiteAuthRepository()
    user = asyncio.run(repo.save_user(User(username="admin", password_hash=hash_password("admin123456"))))
    asyncio.run(repo.assign_roles(user.id, [DEFAULT_ROLE_NAME]))

    from app.main import app

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
    access_token = login.json()["data"]["access_token"]

    response = client.post("/api/auth/logout-all", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
