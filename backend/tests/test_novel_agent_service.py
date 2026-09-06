import pytest

from app.application.services.novel_agent_service import NovelAgentService
from app.domain.entities.novel_runtime import NovelIngestion


class FakeRuntimeRepo:
    def __init__(self):
        self.saved = []

    def get_ingestion(self, novel_id, owner_scope=None):
        return None

    def list_ingestions(self, owner_scope=None):
        return [NovelIngestion(id="ingestion-1", book_id=42, owner_scope="user:1", title="测试", source_text="正文")]

    def save_task(self, task):
        self.saved.append(task)
        return task


class MissingProviderPlatform:
    async def invoke_chat(self, **kwargs):
        raise LookupError("no providers registered for group 'novel_chat'")


class FakePlatform:
    def __init__(self):
        self.calls = []

    async def invoke_chat(self, **kwargs):
        self.calls.append(kwargs)
        return {"provider_name": "test", "model": "test-model", "output": {"ok": True}, "usage": {}}


@pytest.mark.asyncio
async def test_start_analysis_reports_missing_provider_as_service_unavailable():
    service = NovelAgentService(platform=MissingProviderPlatform(), repo=FakeRuntimeRepo())

    with pytest.raises(Exception) as error:
        await service.start_analysis("42", actor_id="1", owner_scope="user:1")

    assert getattr(error.value, "code", None) == "SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_start_analysis_resolves_uploaded_book_id_to_ingestion():
    platform = FakePlatform()
    service = NovelAgentService(platform=platform, repo=FakeRuntimeRepo())

    result = await service.start_analysis("42", actor_id="1", owner_scope="user:1")

    assert platform.calls[0]["provider_group"] == "novel_chat"
    assert result["novel_id"] == "ingestion-1"
    assert result["status"] == "succeeded"
