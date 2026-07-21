import pytest


class NovelAnalysisPlatform:
    def __init__(self):
        self.calls: list[dict] = []

    async def invoke_chat(
        self,
        provider_group: str,
        model: str,
        payload: dict,
        quota_scope: tuple[str, str],
    ) -> dict:
        self.calls.append({"provider_group": provider_group, "model": model})
        return {
            "provider_name": "primary-openai",
            "model": model,
            "output": {
                "summary": "Demo summary",
                "entities": [{"name": "Lin Dong", "type": "character"}],
            },
            "usage": {"input_tokens": 256, "output_tokens": 128, "total_tokens": 384},
        }


@pytest.mark.asyncio
async def test_novel_analysis_pipeline_records_ingestion_task_and_structured_result(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "novel-runtime.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.novel_agent_service import NovelAgentService
    from app.domain.entities.novel_runtime import NovelIngestion
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.novel_runtime_repo_impl import SQLiteNovelRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteNovelRuntimeRepository()
    repo.save_ingestion(
        NovelIngestion(
            id="novel-1",
            title="Demo Novel",
            source_text="A hero enters the world.",
            status="ready",
            pipeline="analysis",
        )
    )
    platform = NovelAnalysisPlatform()
    service = NovelAgentService(platform=platform, repo=repo)

    task = await service.start_analysis("novel-1", actor_id="admin")

    assert task["status"] == "succeeded"
    assert task["provider"] == "primary-openai"
    assert "entities" in task["result"]
    assert platform.calls == [{"provider_group": "novel", "model": None}]


@pytest.mark.asyncio
async def test_novel_analysis_is_scoped_to_the_requesting_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "novel-runtime-owner.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.novel_agent_service import NovelAgentService
    from app.core.exceptions import NotFoundException
    from app.domain.entities.novel_runtime import NovelIngestion
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.novel_runtime_repo_impl import SQLiteNovelRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteNovelRuntimeRepository()
    repo.save_ingestion(NovelIngestion(id="private-ingestion", title="私有书", owner_scope="user:2"))
    service = NovelAgentService(platform=NovelAnalysisPlatform(), repo=repo)

    with pytest.raises(NotFoundException):
        await service.start_analysis("private-ingestion", actor_id="1", owner_scope="user:1")


def test_novel_runtime_legacy_records_can_be_claimed(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "novel-runtime-claim.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.domain.entities.novel_runtime import NovelIngestion
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.novel_runtime_repo_impl import SQLiteNovelRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteNovelRuntimeRepository()
    repo.save_ingestion(NovelIngestion(id="legacy-ingestion", title="旧书", owner_scope="legacy"))

    result = repo.claim_legacy_scope("user:1")

    assert result["ingestions"] == 1
    assert repo.get_ingestion("legacy-ingestion", owner_scope="legacy") is None
    assert repo.get_ingestion("legacy-ingestion", owner_scope="user:1") is not None
