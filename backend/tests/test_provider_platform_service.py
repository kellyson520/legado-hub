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
