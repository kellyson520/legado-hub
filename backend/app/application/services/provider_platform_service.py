from typing import Any, Protocol

from app.infrastructure.providers.base import ProviderAdapter
from app.infrastructure.providers.registry import ProviderRegistry


class ProviderQuotaLimiter(Protocol):
    def assert_allowed(self, quota_scope: tuple[str, str]) -> None:
        raise NotImplementedError


class ProviderPlatformService:
    def __init__(self, registry: ProviderRegistry, quota_limiter: ProviderQuotaLimiter, provider_repo=None):
        self._registry = registry
        self._quota_limiter = quota_limiter
        self._provider_repo = provider_repo

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

    def list_provider_accounts(self) -> list[dict]:
        data = [
            {
                "id": account.id,
                "name": account.name,
                "provider_type": account.provider_type,
                "base_url": account.base_url,
                "api_key_configured": bool(getattr(account, "api_key", "")),
                "default_model": getattr(account, "default_model", ""),
                "model": getattr(account, "default_model", ""),
                "status": "enabled" if account.enabled else "disabled",
                "enabled": account.enabled,
                "created_at": account.created_at.isoformat(),
            }
            for account in (self._provider_repo.list_provider_accounts() if self._provider_repo is not None else [])
        ]
        known_names = {item["name"] for item in data}
        for group, providers in self._registry.snapshot().items():
            for provider in providers:
                if provider.name in known_names:
                    continue
                data.append(
                    {
                        "id": f"runtime:{provider.name}",
                        "name": provider.name,
                        "provider_type": "runtime",
                        "base_url": "",
                        "status": "enabled",
                        "enabled": True,
                        "group": group,
                        "created_at": None,
                    }
                )
                known_names.add(provider.name)
        return data

    def get_llm_settings(self, default_provider_name: str, default_model: str) -> dict:
        account = self._provider_repo.get_llm_provider() if self._provider_repo is not None else None
        if account is None:
            return {
                "provider_name": default_provider_name,
                "providerName": default_provider_name,
                "base_url": "",
                "baseUrl": "",
                "model": default_model,
                "default_model": default_model,
                "api_key_configured": False,
                "apiKeyConfigured": False,
            }
        return self._serialize_llm_settings(account, default_model=default_model)

    def save_llm_settings(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
        model: str,
    ) -> dict:
        if self._provider_repo is None:
            raise RuntimeError("provider repository is not configured")
        account = self._provider_repo.upsert_llm_provider(
            name=provider_name,
            base_url=base_url,
            api_key=api_key,
            default_model=model,
        )
        return self._serialize_llm_settings(account, default_model=model)

    def list_quota_policies(self) -> list[dict]:
        if self._provider_repo is None:
            return []
        return [
            {
                "id": quota.id,
                "scope_type": quota.scope_type,
                "scope_id": quota.scope_id,
                "scope": f"{quota.scope_type}:{quota.scope_id}",
                "dailyCostLimit": quota.daily_cost_limit,
                "daily_cost_limit": quota.daily_cost_limit,
                "created_at": quota.created_at.isoformat(),
            }
            for quota in self._provider_repo.list_quota_policies()
        ]

    @staticmethod
    def _serialize_llm_settings(account, *, default_model: str) -> dict:
        model = getattr(account, "default_model", "") or default_model
        return {
            "provider_name": account.name,
            "providerName": account.name,
            "base_url": account.base_url,
            "baseUrl": account.base_url,
            "model": model,
            "default_model": model,
            "api_key_configured": bool(getattr(account, "api_key", "")),
            "apiKeyConfigured": bool(getattr(account, "api_key", "")),
        }

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
