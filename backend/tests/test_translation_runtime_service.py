import pytest


class FlakyTranslationPlatform:
    def __init__(self):
        self.calls = 0

    async def invoke_chat(
        self,
        provider_group: str,
        model: str,
        payload: dict,
        quota_scope: tuple[str, str],
    ) -> dict:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary provider error")
        text = payload["text"]
        return {
            "provider_name": "primary-openai",
            "model": model,
            "output": {"text": text.lower()},
            "usage": {"input_tokens": len(text), "output_tokens": len(text), "total_tokens": len(text) * 2},
        }


@pytest.mark.asyncio
async def test_translation_service_splits_large_text_and_retries_failed_chunks(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "translation-runtime.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.translation_service import TranslationService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.translation_runtime_repo_impl import (
        SQLiteTranslationRuntimeRepository,
    )

    bootstrap_sqlite()
    platform = FlakyTranslationPlatform()
    service = TranslationService(platform=platform, repo=SQLiteTranslationRuntimeRepository())

    job = await service.create_job(
        {"text": "A" * 9000, "source_language": "zh", "target_language": "en"},
        actor_id="admin",
    )

    assert job["chunk_count"] > 1
    assert all(chunk["status"] == "succeeded" for chunk in job["chunks"])
    assert job["chunks"][0]["attempt_count"] == 2
    assert platform.calls > job["chunk_count"]

    rows = await service.list_jobs()
    assert rows[0]["id"] == job["id"]
