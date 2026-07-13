from typing import Any, Protocol

from app.infrastructure.providers.base import ProviderAdapter
from app.infrastructure.providers.registry import ProviderRegistry


class ProviderQuotaLimiter(Protocol):
    def assert_allowed(self, quota_scope: tuple[str, str]) -> None:
        raise NotImplementedError


class ProviderPlatformService:
    def __init__(self, registry: ProviderRegistry, quota_limiter: ProviderQuotaLimiter):
        self._registry = registry
        self._quota_limiter = quota_limiter

    async def invoke_chat(
        self,
        provider_group: str,
        model: str,
        payload: dict[str, Any],
        quota_scope: tuple[str, str],
    ) -> dict[str, Any]:
        self._quota_limiter.assert_allowed(quota_scope)
        providers = self._registry.resolve_group(provider_group)
        last_error: Exception | None = None

        for attempt_count, provider in enumerate(providers, start=1):
            try:
                result = await provider.invoke_chat(model=model, payload=payload)
                return self._normalize_result(
                    result=result,
                    provider=provider,
                    provider_group=provider_group,
                    model=model,
                    attempt_count=attempt_count,
                )
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise LookupError(f"no providers registered for group '{provider_group}'")

    @staticmethod
    def _normalize_result(
        result: dict[str, Any],
        provider: ProviderAdapter,
        provider_group: str,
        model: str,
        attempt_count: int,
    ) -> dict[str, Any]:
        normalized = dict(result)
        normalized.setdefault("provider_name", provider.name)
        normalized.setdefault("provider_group", provider_group)
        normalized.setdefault("model", model)
        normalized.setdefault("attempt_count", attempt_count)
        return normalized
