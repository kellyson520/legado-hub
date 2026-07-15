import httpx
import pytest


class StubProvider:
    def __init__(self, name: str, *, error: Exception | None = None, result: dict | None = None):
        self.name = name
        self.error = error
        self.result = result or {"output": {"text": "ok"}}
        self.models: list[str] = []

    async def invoke_chat(self, model: str, payload: dict) -> dict:
        self.models.append(model)
        if self.error is not None:
            raise self.error
        return {"provider_name": self.name, "model": model, **self.result}


class AllowAllQuotaLimiter:
    def assert_allowed(self, quota_scope):
        return None


@pytest.mark.asyncio
async def test_platform_uses_backup_route_model_after_primary_timeout():
    from app.application.services.provider_platform_service import ProviderPlatformService
    from app.infrastructure.providers.registry import ProviderRegistry, ProviderSelection

    primary = StubProvider("primary", error=httpx.ReadTimeout("timed out"))
    backup = StubProvider("backup")
    service = ProviderPlatformService(
        registry=ProviderRegistry(
            {
                "source_build": [
                    ProviderSelection(primary, "primary-model"),
                    ProviderSelection(backup, "backup-model"),
                ]
            }
        ),
        quota_limiter=AllowAllQuotaLimiter(),
    )

    result = await service.invoke_chat(
        provider_group="source_build",
        model=None,
        payload={"messages": []},
        quota_scope=("user", "1"),
    )

    assert primary.models == ["primary-model"]
    assert backup.models == ["backup-model"]
    assert (result["provider_name"], result["model"], result["attempt_count"]) == ("backup", "backup-model", 2)


@pytest.mark.asyncio
async def test_platform_stops_after_a_422_request_error():
    from app.application.services.provider_platform_service import ProviderPlatformService
    from app.infrastructure.providers.registry import ProviderRegistry, ProviderSelection

    primary = StubProvider(
        "primary",
        error=httpx.HTTPStatusError(
            "invalid request",
            request=httpx.Request("POST", "https://primary.example"),
            response=httpx.Response(422),
        ),
    )
    backup = StubProvider("backup")
    service = ProviderPlatformService(
        registry=ProviderRegistry(
            {"ai": [ProviderSelection(primary, "primary-model"), ProviderSelection(backup, "backup-model")]}
        ),
        quota_limiter=AllowAllQuotaLimiter(),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await service.invoke_chat(
            provider_group="ai",
            model=None,
            payload={"messages": []},
            quota_scope=("user", "1"),
        )

    assert backup.models == []


@pytest.mark.asyncio
async def test_platform_exhaustion_sanitizes_provider_failures():
    from app.application.services.provider_platform_service import ProviderInvocationError, ProviderPlatformService
    from app.infrastructure.providers.registry import ProviderRegistry, ProviderSelection

    service = ProviderPlatformService(
        registry=ProviderRegistry(
            {
                "translation": [
                    ProviderSelection(StubProvider("primary", error=RuntimeError("Authorization: Bearer sk-secret-value")), "a"),
                    ProviderSelection(StubProvider("backup", error=httpx.ReadTimeout("timed out")), "b"),
                ]
            }
        ),
        quota_limiter=AllowAllQuotaLimiter(),
    )

    with pytest.raises(ProviderInvocationError) as error:
        await service.invoke_chat(
            provider_group="translation",
            model=None,
            payload={"messages": []},
            quota_scope=("user", "1"),
        )

    assert error.value.failures[0] == "primary: Authorization: Bearer [redacted]"
    assert "sk-secret-value" not in str(error.value)
