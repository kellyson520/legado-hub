import pytest


class FailingProvider:
    name = "primary-openai"

    async def invoke_chat(self, model: str, payload: dict):
        raise RuntimeError("provider failed")


class WorkingProvider:
    name = "secondary-openai"

    async def invoke_chat(self, model: str, payload: dict):
        return {
            "provider_name": self.name,
            "model": model,
            "attempt_count": 2,
            "output": {"text": "hello"},
        }

    async def invoke_embedding(self, model: str, payload: dict):
        return {
            "provider_name": self.name,
            "model": model,
            "data": [{"embedding": [1.0, 0.0], "index": 0}],
            "usage": {"input_tokens": 2, "total_tokens": 2},
        }


class AllowAllQuotaLimiter:
    def assert_allowed(self, quota_scope):
        return None


class DenyQuotaLimiter:
    def assert_allowed(self, quota_scope):
        raise RuntimeError("quota exceeded")


@pytest.mark.asyncio
async def test_platform_service_retries_then_falls_back_to_secondary_provider():
    from app.application.services.provider_platform_service import ProviderPlatformService
    from app.infrastructure.providers.registry import ProviderRegistry

    registry = ProviderRegistry({"default": [FailingProvider(), WorkingProvider()]})
    service = ProviderPlatformService(registry=registry, quota_limiter=AllowAllQuotaLimiter())

    result = await service.invoke_chat(
        provider_group="default",
        model="gpt-4.1-mini",
        payload={"messages": [{"role": "user", "content": "hello"}]},
        quota_scope=("user", "admin"),
    )

    assert result["provider_name"] == "secondary-openai"
    assert result["attempt_count"] == 2


@pytest.mark.asyncio
async def test_platform_service_blocks_requests_after_quota_exhaustion():
    from app.application.services.provider_platform_service import ProviderPlatformService
    from app.infrastructure.providers.registry import ProviderRegistry

    registry = ProviderRegistry({"default": [WorkingProvider()]})
    service = ProviderPlatformService(registry=registry, quota_limiter=DenyQuotaLimiter())

    with pytest.raises(RuntimeError, match="quota exceeded"):
        await service.invoke_chat(
            provider_group="default",
            model="gpt-4.1-mini",
            payload={},
            quota_scope=("user", "admin"),
        )


@pytest.mark.asyncio
async def test_platform_exposes_novel_task_routes_through_existing_provider_chain():
    from app.application.services.provider_platform_service import PROVIDER_ROUTE_GROUPS, ProviderPlatformService
    from app.infrastructure.providers.registry import ProviderRegistry

    provider = WorkingProvider()
    service = ProviderPlatformService(
        registry=ProviderRegistry({"novel_chat": [provider], "novel_embedding": [provider]}),
        quota_limiter=AllowAllQuotaLimiter(),
    )

    chat = await service.invoke_novel_chat(
        owner_scope="user:1", model="novel-model", payload={"messages": []}, quota_scope=("user", "1")
    )
    embedding = await service.invoke_novel_embedding(
        owner_scope="user:1", model="embedding-model", payload={"input": ["正文"]}, quota_scope=("user", "1")
    )

    assert chat["provider_group"] == "novel_chat"
    assert embedding["data"][0]["embedding"] == [1.0, 0.0]
    assert {"novel_chat", "novel_extract", "novel_summary", "novel_embedding"}.issubset(
        set(PROVIDER_ROUTE_GROUPS)
    )
