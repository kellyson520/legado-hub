import pytest


class FailingPlatform:
    async def invoke_chat(self, **_kwargs) -> dict:
        raise RuntimeError("401 Bearer super-secret")


class RecordingPlatform:
    def __init__(self):
        self.calls: list[dict] = []

    async def invoke_chat(
        self,
        provider_group: str,
        model: str,
        payload: dict,
        quota_scope: tuple[str, str],
    ) -> dict:
        self.calls.append(
            {
                "provider_group": provider_group,
                "model": model,
                "payload": payload,
                "quota_scope": quota_scope,
            }
        )
        return {
            "provider_name": "primary-openai",
            "model": model,
            "output": {"text": '{"summary":"ok"}'},
            "usage": {"input_tokens": 128, "output_tokens": 64, "total_tokens": 192},
            "cost": {"total": 0.12},
        }


@pytest.mark.asyncio
async def test_ai_service_records_provider_model_usage_and_result(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ai-runtime.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.ai_service import AIService
    from app.infrastructure.persistence.sqlite.ai_runtime_repo_impl import SQLiteAIRuntimeRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    platform = RecordingPlatform()
    service = AIService(platform=platform, repo=SQLiteAIRuntimeRepository())

    task = await service.run_character_analysis(
        {"title": "Demo", "content": "Story", "model": "gpt-4.1-mini"},
        actor_id="admin",
    )

    assert task["provider"] == "primary-openai"
    assert task["model"] == "gpt-4.1-mini"
    assert task["usage"]["input_tokens"] > 0
    assert task["status"] == "succeeded"
    assert platform.calls[0]["quota_scope"] == ("user", "admin")

    rows = await service.list_tasks()
    assert rows[0]["id"] == task["id"]


@pytest.mark.asyncio
async def test_source_build_failure_is_persisted_without_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ai-runtime.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.ai_service import AIService
    from app.infrastructure.persistence.sqlite.ai_runtime_repo_impl import SQLiteAIRuntimeRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    service = AIService(platform=FailingPlatform(), repo=SQLiteAIRuntimeRepository())
    task = await service.run_source_build_repair(
        {"source_version_id": "sv-1", "agent_run_id": "run-1", "url": "https://example.test"},
        actor_id="tenant-1",
    )

    assert task["status"] == "failed"
    assert task["type"] == "source_build_repair"
    assert "super-secret" not in str(task["result"])
    assert (await service.list_tasks())[0]["id"] == task["id"]


@pytest.mark.asyncio
async def test_source_build_success_records_linked_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ai-runtime.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.ai_service import AIService
    from app.infrastructure.persistence.sqlite.ai_runtime_repo_impl import SQLiteAIRuntimeRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    async def successful_runner():
        return {"provider_name": "test", "model": "test-model", "output": {"text": "ok"}}

    bootstrap_sqlite()
    service = AIService(platform=RecordingPlatform(), repo=SQLiteAIRuntimeRepository())
    task = await service.run_source_build_repair(
        {"source_version_id": "sv-2", "agent_run_id": "run-2", "url": "https://example.test"},
        actor_id="tenant-1",
        runner=successful_runner,
    )

    assert task["status"] == "succeeded"
    assert task["result"]["source_version_id"] == "sv-2"
    assert task["result"]["agent_run_id"] == "run-2"
