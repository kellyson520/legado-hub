from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone


def test_system_provider_api_lists_health_and_quota_state(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "system-provider.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.provider_repo_impl import SQLiteProviderRepository
    from app.main import app

    bootstrap_sqlite()
    repo = SQLiteProviderRepository()
    provider = repo.create_provider_account(
        name="primary-openai",
        provider_type="openai_compatible",
        base_url="https://api.example.com",
    )
    repo.create_quota_policy(scope_type="user", scope_id="admin", daily_cost_limit=50)

    client = TestClient(app)
    token = create_access_token(
        {"sub": "1", "permissions": ["system.settings.manage"], "sid": "provider-platform-1"}
    )
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/system/providers", headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"][0]["name"] == provider.name

    quota_response = client.get("/api/system/quotas", headers=headers)
    assert quota_response.status_code == 200
    assert quota_response.json()["data"][0]["scope"] == "user:admin"


def test_translation_jobs_api_returns_chunk_usage(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "translation-jobs.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.domain.entities.translation_runtime import TranslationChunk, TranslationJob
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.translation_runtime_repo_impl import (
        SQLiteTranslationRuntimeRepository,
    )
    from app.main import app

    bootstrap_sqlite()
    repo = SQLiteTranslationRuntimeRepository()
    repo.save_job(
        TranslationJob(
            id="tr-job-1",
            actor_id="admin",
            source_language="zh",
            target_language="en",
            status="succeeded",
            provider="primary-openai",
            model="gpt-4.1-mini",
            source_text="测试文本",
            result_text="test text",
            chunk_count=1,
            chunks=[
                TranslationChunk(
                    id="tr-chunk-1",
                    job_id="tr-job-1",
                    chunk_index=0,
                    source_text="测试文本",
                    translated_text="test text",
                    status="succeeded",
                    provider="primary-openai",
                    model="gpt-4.1-mini",
                    usage={"input_tokens": 10, "output_tokens": 8, "total_tokens": 18},
                    attempt_count=1,
                )
            ],
        )
    )

    client = TestClient(app)
    token = create_access_token(
        {"sub": "1", "permissions": ["translation.run"], "sid": "provider-platform-2"}
    )
    response = client.get("/api/translation/jobs", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert "chunks" in response.json()["data"][0]
    assert response.json()["data"][0]["chunks"][0]["usage"]["input_tokens"] == 10


def test_operations_review_queue_can_mark_translation_job_reviewed(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "translation-review-queue.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.domain.entities.translation_runtime import TranslationJob
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.translation_runtime_repo_impl import (
        SQLiteTranslationRuntimeRepository,
    )
    from app.main import app

    bootstrap_sqlite()
    repo = SQLiteTranslationRuntimeRepository()
    repo.save_job(
        TranslationJob(
            id="tr-job-review-1",
            actor_id="translator",
            source_language="zh",
            target_language="en",
            status="succeeded",
            provider="primary-openai",
            model="gpt-4.1-mini",
            source_text="原文内容",
            result_text="translated",
            review_status="candidate",
            chunk_count=1,
        )
    )

    client = TestClient(app)
    token = create_access_token(
        {"sub": "1", "permissions": ["translation.run", "agent_runs.write"], "sid": "provider-platform-2b"}
    )
    response = client.post(
        "/api/events/review-queue/tr-job-review-1/resolve",
        headers={"Authorization": f"Bearer {token}"},
        json={"item_type": "translation_job", "action": "review"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["queue_item_id"] == "tr-job-review-1"
    assert response.json()["data"]["status"] == "reviewed"


def test_system_provider_api_surfaces_env_runtime_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "system-provider-env.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    monkeypatch.setenv("LLM_API_URL", "https://api.example.com/v1/chat/completions")
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    client = TestClient(app)
    token = create_access_token(
        {"sub": "1", "permissions": ["system.settings.manage"], "sid": "provider-platform-3"}
    )
    response = client.get("/api/system/providers", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["data"][0]["name"] == "local-llm"


def test_system_provider_api_persists_llm_settings_and_registry_uses_them(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "system-provider-llm-settings.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    monkeypatch.delenv("LLM_API_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_provider_registry
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    client = TestClient(app)
    token = create_access_token(
        {"sub": "1", "permissions": ["system.settings.manage"], "sid": "provider-platform-4"}
    )
    headers = {"Authorization": f"Bearer {token}"}

    empty = client.get("/api/system/llm-settings", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["data"]["api_key_configured"] is False

    saved = client.put(
        "/api/system/llm-settings",
        headers=headers,
        json={
            "provider_name": "Primary OpenAI",
            "base_url": "https://api.openai.test/v1",
            "api_key": "sk-test",
            "model": "gpt-4.1-mini",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["provider_name"] == "Primary OpenAI"
    assert saved.json()["data"]["api_key_configured"] is True

    listed = client.get("/api/system/providers", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["data"][0]["name"] == "Primary OpenAI"

    snapshot = build_provider_registry().snapshot()
    assert snapshot["default"][0].name == "Primary OpenAI"

    renamed = client.put(
        "/api/system/llm-settings",
        headers=headers,
        json={
            "provider_name": "Renamed OpenAI",
            "base_url": "https://api.renamed.test/v1",
            "api_key": "sk-renamed",
            "model": "gpt-4.1",
        },
    )
    assert renamed.status_code == 200
    updated_snapshot = build_provider_registry().snapshot()
    assert updated_snapshot["default"][0].name == "Renamed OpenAI"
    assert updated_snapshot["default"][0].model == "gpt-4.1"


def test_system_provider_management_discovers_models_without_leaking_key(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "provider-management.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    monkeypatch.delenv("LLM_API_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.providers.openai_compatible import OpenAICompatibleProvider
    from app.main import app

    async def fake_list_models(self):
        return ["gpt-b", "gpt-a"]

    monkeypatch.setattr(OpenAICompatibleProvider, "list_models", fake_list_models, raising=False)
    bootstrap_sqlite()
    client = TestClient(app)
    token = create_access_token(
        {"sub": "1", "permissions": ["system.settings.manage"], "sid": "provider-management-1"}
    )
    headers = {"Authorization": f"Bearer {token}"}

    saved = client.post(
        "/api/system/providers",
        headers=headers,
        json={
            "name": "primary",
            "base_url": "https://api.example/v1",
            "api_key": "sk-secret",
            "default_model": "",
            "enabled": True,
        },
    )

    assert saved.status_code == 200
    provider_id = saved.json()["data"]["id"]
    models = client.post(f"/api/system/providers/{provider_id}/models", headers=headers)
    listed = client.get("/api/system/providers", headers=headers)
    route = client.put(
        "/api/system/provider-routes/ai",
        headers=headers,
        json={"entries": [{"provider_account_id": provider_id, "model": "gpt-b"}]},
    )

    assert models.json()["data"] == ["gpt-a", "gpt-b"]
    assert "sk-secret" not in str(listed.json())
    assert route.json()["data"]["entries"][0]["model"] == "gpt-b"

    disabled_route = client.put(
        "/api/system/provider-routes/translation",
        headers=headers,
        json={"entries": [{"provider_account_id": provider_id, "model": "gpt-b", "enabled": False}]},
    )
    assert disabled_route.status_code == 422


def test_system_provider_management_reports_rejected_provider_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "provider-management-auth.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    import httpx

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.providers.openai_compatible import OpenAICompatibleProvider
    from app.main import app

    async def rejected_list_models(self):
        raise httpx.HTTPStatusError(
            "unauthorized",
            request=httpx.Request("GET", "https://provider.example/v1/models"),
            response=httpx.Response(401),
        )

    monkeypatch.setattr(OpenAICompatibleProvider, "list_models", rejected_list_models, raising=False)
    bootstrap_sqlite()
    client = TestClient(app)
    token = create_access_token(
        {"sub": "1", "permissions": ["system.settings.manage"], "sid": "provider-management-auth"}
    )
    headers = {"Authorization": f"Bearer {token}"}
    saved = client.post(
        "/api/system/providers",
        headers=headers,
        json={
            "name": "rejected",
            "base_url": "https://provider.example/v1",
            "api_key": "invalid-key",
            "default_model": "",
            "enabled": True,
        },
    )

    response = client.post(f"/api/system/providers/{saved.json()['data']['id']}/models", headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"] == "Provider authentication failed; update the API key"


def test_system_provider_api_preserves_future_activation_schedule(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "provider-schedule-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    client = TestClient(app)
    token = create_access_token(
        {"sub": "1", "permissions": ["system.settings.manage"], "sid": "provider-schedule"}
    )
    activation_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    response = client.post(
        "/api/system/providers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "scheduled-provider",
            "base_url": "https://api.example.test/v1",
            "api_key": "sk-scheduled",
            "default_model": "kimi-k3",
            "enabled": True,
            "activation_at": activation_at,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "scheduled"
    assert response.json()["data"]["api_key_configured"] is True

    legacy = client.get("/api/system/llm-settings", headers={"Authorization": f"Bearer {token}"})
    assert legacy.status_code == 200
    assert legacy.json()["data"]["provider_name"] != "scheduled-provider"
    assert legacy.json()["data"]["api_key_configured"] is False
