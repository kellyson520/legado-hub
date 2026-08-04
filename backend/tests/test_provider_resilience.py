import asyncio
from types import SimpleNamespace

import pytest


class FlakyProvider:
    name = "flaky"

    def __init__(self, failures=2):
        self.failures = failures
        self.calls = 0

    async def invoke_chat(self, model: str, payload: dict):
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("temporary timeout")
        return {
            "model": model,
            "output": {"text": "ok"},
            "cost": {"total": 0.01},
        }


@pytest.mark.asyncio
async def test_provider_retries_the_same_provider_with_a_bounded_backoff(monkeypatch):
    from app.application.services import provider_platform_service as module
    from app.application.services.provider_platform_service import ProviderPlatformService
    from app.infrastructure.providers.registry import ProviderRegistry

    sleeps = []

    async def fake_sleep(value):
        sleeps.append(value)

    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)
    provider = FlakyProvider(failures=2)
    service = ProviderPlatformService(
        registry=ProviderRegistry({"default": [provider]}),
        quota_limiter=SimpleNamespace(assert_allowed=lambda _scope: None),
        max_retries=2,
        retry_base_delay=0.25,
        retry_jitter=0,
    )

    result = await service.invoke_chat(
        provider_group="default",
        model="m",
        payload={},
        quota_scope=("user", "1"),
    )

    assert result["output"]["text"] == "ok"
    assert provider.calls == 3
    assert sleeps == [0.25, 0.5]


@pytest.mark.asyncio
async def test_repository_quota_limiter_records_cost_and_blocks_the_next_request():
    from app.application.services.provider_platform_service import (
        ProviderPlatformService,
        ProviderQuotaExceeded,
        RepositoryProviderQuotaLimiter,
    )
    from app.infrastructure.providers.registry import ProviderRegistry

    repo = SimpleNamespace(
        list_quota_policies=lambda: [
            SimpleNamespace(scope_type="user", scope_id="1", daily_cost_limit=0.01),
        ],
    )
    provider = FlakyProvider(failures=0)
    limiter = RepositoryProviderQuotaLimiter(repo)
    service = ProviderPlatformService(
        registry=ProviderRegistry({"default": [provider]}),
        quota_limiter=limiter,
    )

    await service.invoke_chat(
        provider_group="default", model="m", payload={}, quota_scope=("user", "1"),
    )
    with pytest.raises(ProviderQuotaExceeded):
        await service.invoke_chat(
            provider_group="default", model="m", payload={}, quota_scope=("user", "1"),
        )


@pytest.mark.asyncio
async def test_repository_quota_limiter_does_not_admit_concurrent_requests_past_cost_limit():
    from app.application.services.provider_platform_service import (
        ProviderPlatformService,
        ProviderQuotaExceeded,
        RepositoryProviderQuotaLimiter,
    )
    from app.infrastructure.providers.registry import ProviderRegistry

    class BlockingProvider:
        name = "blocking"

        def __init__(self):
            self.calls = 0
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def invoke_chat(self, model: str, payload: dict):
            self.calls += 1
            self.started.set()
            await self.release.wait()
            return {"model": model, "output": {"text": "ok"}, "cost": {"total": 0.01}}

    repo = SimpleNamespace(
        list_quota_policies=lambda: [
            SimpleNamespace(scope_type="user", scope_id="1", daily_cost_limit=0.01),
        ],
    )
    provider = BlockingProvider()
    service = ProviderPlatformService(
        registry=ProviderRegistry({"default": [provider]}),
        quota_limiter=RepositoryProviderQuotaLimiter(repo),
        max_retries=0,
    )

    first = asyncio.create_task(
        service.invoke_chat(provider_group="default", model="m", payload={}, quota_scope=("user", "1"))
    )
    await provider.started.wait()
    second = asyncio.create_task(
        service.invoke_chat(provider_group="default", model="m", payload={}, quota_scope=("user", "1"))
    )
    await asyncio.sleep(0)
    provider.release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)

    assert sum(isinstance(result, ProviderQuotaExceeded) for result in results) == 1
    assert sum(isinstance(result, dict) for result in results) == 1
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_provider_failure_aggregation_redacts_credentials_from_every_provider():
    from app.application.services.provider_platform_service import ProviderInvocationError, ProviderPlatformService
    from app.infrastructure.providers.registry import ProviderRegistry

    class BrokenProvider:
        def __init__(self, name: str, secret: str):
            self.name = name
            self.secret = secret

        async def invoke_chat(self, model: str, payload: dict):
            raise RuntimeError(
                f"POST https://provider.invalid/v1?api_key={self.secret} "
                f"Authorization: Bearer {self.secret}"
            )

    first_secret = "first-secret"
    second_secret = "second-secret"
    service = ProviderPlatformService(
        registry=ProviderRegistry(
            {
                "default": [
                    BrokenProvider("first", first_secret),
                    BrokenProvider("second", second_secret),
                ]
            }
        ),
        quota_limiter=SimpleNamespace(assert_allowed=lambda _scope: None),
        max_retries=0,
    )

    with pytest.raises(ProviderInvocationError) as error:
        await service.invoke_chat(
            provider_group="default", model="m", payload={}, quota_scope=("user", "1")
        )

    message = str(error.value)
    assert "first" in message and "second" in message
    assert first_secret not in message
    assert second_secret not in message
    assert "api_key=[redacted]" in message


@pytest.mark.asyncio
async def test_legacy_provider_stream_preserves_typed_http_errors():
    from app.services.novel_agent.providers import ProviderConfig, ProviderHTTPError
    from app.services.novel_agent.providers.openai_provider import OpenAIProvider

    class Response:
        status_code = 429

        async def aread(self):
            return b"rate limited"

    class StreamContext:
        async def __aenter__(self):
            return Response()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class Client:
        def stream(self, *args, **kwargs):
            return StreamContext()

    provider = OpenAIProvider(ProviderConfig(name="test", base_url="https://provider.invalid", model="m"))
    provider._client = Client()

    chunks = [chunk async for chunk in provider.stream([])]
    assert isinstance(chunks[0].exception, ProviderHTTPError)
    with pytest.raises(ProviderHTTPError):
        await provider.complete([])
