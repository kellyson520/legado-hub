from fastapi.testclient import TestClient


def test_provider_api_persists_anthropic_type_and_builds_matching_adapter(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "provider-type-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    monkeypatch.delenv("LLM_API_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_provider_registry
    from app.infrastructure.providers.anthropic import AnthropicProvider
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    token = create_access_token(
        {"sub": "1", "permissions": ["system.settings.manage"], "roles": []}
    )
    headers = {"Authorization": f"Bearer {token}"}
    response = TestClient(app).post(
        "/api/system/providers",
        headers=headers,
        json={
            "name": "claude",
            "provider_type": "anthropic",
            "base_url": "https://api.anthropic.com",
            "api_key": "anthropic-secret",
            "default_model": "claude-3-7-sonnet",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["provider_type"] == "anthropic"
    selection = build_provider_registry().snapshot()["ai"][0]
    assert isinstance(selection.provider, AnthropicProvider)
    assert selection.model == "claude-3-7-sonnet"
