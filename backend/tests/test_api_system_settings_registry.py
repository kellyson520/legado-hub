from fastapi.testclient import TestClient


def build_client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "system-settings-registry.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    token = create_access_token(
        {"sub": "1", "permissions": ["system.settings.manage"], "sid": "settings-registry-1"}
    )
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def test_settings_section_returns_normalized_value_and_rejects_stale_save(monkeypatch, tmp_path):
    client, headers = build_client(monkeypatch, tmp_path)

    initial = client.get("/api/system/settings/agents/budgets", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["data"]["value"]["max_tool_calls_per_task"] == 24

    first_save = client.put(
        "/api/system/settings/agents/budgets",
        headers=headers,
        json={
            "value": {"max_tool_calls_per_task": 999},
            "expected_version": initial.json()["data"]["version"],
        },
    )
    assert first_save.status_code == 200
    assert first_save.json()["data"]["value"]["max_tool_calls_per_task"] == 100

    stale_save = client.put(
        "/api/system/settings/agents/budgets",
        headers=headers,
        json={
            "value": {"max_tool_calls_per_task": 2},
            "expected_version": initial.json()["data"]["version"],
        },
    )
    assert stale_save.status_code == 409


def test_agent_roles_reject_an_unknown_provider_route_group(monkeypatch, tmp_path):
    client, headers = build_client(monkeypatch, tmp_path)

    response = client.put(
        "/api/system/settings/agents/roles",
        headers=headers,
        json={
            "value": {"extractor_route_group": "missing-route"},
            "expected_version": None,
        },
    )

    assert response.status_code == 422


def test_agent_roles_accept_the_registered_novel_route_groups(monkeypatch, tmp_path):
    client, headers = build_client(monkeypatch, tmp_path)

    response = client.put(
        "/api/system/settings/agents/roles",
        headers=headers,
        json={
            "value": {
                "extractor_route_group": "novel_extract",
                "verifier_route_group": "novel_verify",
                "adjudicator_route_group": "novel_adjudicate",
                "auditor_route_group": "novel_audit",
            },
            "expected_version": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["value"]["auditor_route_group"] == "novel_audit"
