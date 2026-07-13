from fastapi.testclient import TestClient


def test_admin_route_requires_permission(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "admin-rbac.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    denied = create_access_token({"sub": "1", "permissions": ["dashboard.read"], "sid": "s-1"})
    denied_response = client.get("/api/admin/users", headers={"Authorization": f"Bearer {denied}"})
    assert denied_response.status_code == 403

    allowed = create_access_token({"sub": "1", "permissions": ["users.read"], "sid": "s-2"})
    allowed_response = client.get("/api/admin/users", headers={"Authorization": f"Bearer {allowed}"})
    assert allowed_response.status_code == 200
