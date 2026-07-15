from fastapi.testclient import TestClient


def build_client(monkeypatch, tmp_path, permissions: list[str]):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "system-settings.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    monkeypatch.delenv("LLM_API_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    token = create_access_token(
        {"sub": "1", "permissions": permissions, "sid": "system-settings-1"}
    )
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def test_source_build_agent_setting_defaults_disabled_and_persists(monkeypatch, tmp_path):
    client, headers = build_client(monkeypatch, tmp_path, ["system.settings.manage"])

    initial = client.get("/api/system/source-build-agent-settings", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["data"] == {"enabled": False, "provider_configured": False}

    updated = client.put(
        "/api/system/source-build-agent-settings",
        headers=headers,
        json={"enabled": True},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["enabled"] is True

    persisted = client.get("/api/system/source-build-agent-settings", headers=headers)
    assert persisted.status_code == 200
    assert persisted.json()["data"]["enabled"] is True


def test_source_build_agent_setting_rejects_missing_permission(monkeypatch, tmp_path):
    client, headers = build_client(monkeypatch, tmp_path, [])

    get_response = client.get("/api/system/source-build-agent-settings", headers=headers)
    put_response = client.put(
        "/api/system/source-build-agent-settings",
        headers=headers,
        json={"enabled": True},
    )

    assert get_response.status_code == 403
    assert put_response.status_code == 403


def test_interactive_browser_settings_default_disabled_and_persist(monkeypatch, tmp_path):
    client, headers = build_client(monkeypatch, tmp_path, ['system.settings.manage'])

    initial = client.get('/api/system/interactive-browser-settings', headers=headers)
    assert initial.status_code == 200
    assert initial.json()['data'] == {
        'enabled': False,
        'automatic_enabled': True,
        'max_sessions': 1,
        'session_timeout_seconds': 300,
    }

    updated = client.put(
        '/api/system/interactive-browser-settings',
        headers=headers,
        json={
            'enabled': True,
            'automatic_enabled': False,
            'max_sessions': 2,
            'session_timeout_seconds': 180,
        },
    )

    assert updated.status_code == 200
    assert updated.json()['data'] == {
        'enabled': True,
        'automatic_enabled': False,
        'max_sessions': 2,
        'session_timeout_seconds': 180,
    }


def test_source_build_agent_availability_uses_source_build_route():
    from app.application.services.system_settings_service import SystemSettingsService

    class SettingsRepo:
        def get_bool(self, _key, default):
            return default

    class Registry:
        def resolve_group(self, group):
            if group == "source_build":
                raise LookupError("source build route missing")
            return [object()]

    settings = SystemSettingsService(SettingsRepo(), Registry()).get_source_build_agent_settings()

    assert settings["provider_configured"] is False
