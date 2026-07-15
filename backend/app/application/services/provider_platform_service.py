from typing import Any, Protocol

from app.infrastructure.providers.base import ProviderAdapter
from app.infrastructure.providers.openai_compatible import OpenAICompatibleProvider
from app.infrastructure.providers.registry import ProviderRegistry


PROVIDER_ROUTE_GROUPS = ("default", "ai", "source_build", "translation", "novel")


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
            self._serialize_provider_account(account)
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

    def save_provider(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
        enabled: bool,
        provider_id: str | None = None,
    ) -> dict:
        if self._provider_repo is None:
            raise RuntimeError("provider repository is not configured")
        if provider_id is not None and self._provider_repo.get_provider(provider_id) is None:
            raise LookupError("provider not found")
        account = self._provider_repo.save_provider(
            id=provider_id,
            name=name,
            base_url=base_url,
            api_key=api_key,
            default_model=default_model,
            enabled=enabled,
        )
        self._ensure_initial_routes()
        return self._serialize_provider_account(account)

    async def discover_models(self, provider_id: str) -> list[str]:
        if self._provider_repo is None:
            raise RuntimeError("provider repository is not configured")
        account = self._provider_repo.get_provider(provider_id)
        if account is None:
            raise LookupError("provider not found")
        if not account.enabled or not account.base_url or not account.api_key:
            raise ValueError("provider must be enabled and configured before models can be fetched")
        provider = OpenAICompatibleProvider(
            name=account.name,
            endpoint_url=account.base_url,
            api_key=account.api_key,
        )
        try:
            return sorted(set(await provider.list_models()))
        finally:
            await provider.aclose()

    def get_routes(self, provider_group: str) -> dict:
        self._validate_provider_group(provider_group)
        if self._provider_repo is None:
            return {"group": provider_group, "entries": []}
        return {
            "group": provider_group,
            "entries": [self._serialize_route(route) for route in self._provider_repo.list_routes(provider_group)],
        }

    def replace_routes(self, provider_group: str, entries: list[dict]) -> dict:
        self._validate_provider_group(provider_group)
        if self._provider_repo is None:
            raise RuntimeError("provider repository is not configured")
        if not entries:
            raise ValueError("at least one provider route entry is required")
        normalized_entries: list[dict] = []
        for entry in entries:
            provider_id = str(entry.get("provider_account_id") or "")
            model = str(entry.get("model") or "").strip()
            account = self._provider_repo.get_provider(provider_id)
            if account is None:
                raise LookupError("route provider not found")
            if not account.enabled or not account.base_url or not account.api_key:
                raise ValueError("route provider must be enabled and configured")
            if not model:
                raise ValueError("route model is required")
            normalized_entries.append(
                {
                    "provider_account_id": account.id,
                    "model": model,
                    "enabled": bool(entry.get("enabled", True)),
                }
            )
        routes = self._provider_repo.replace_routes(provider_group, normalized_entries)
        return {"group": provider_group, "entries": [self._serialize_route(route) for route in routes]}

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
        self._ensure_initial_routes()
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

    @classmethod
    def _serialize_provider_account(cls, account) -> dict:
        api_key = str(getattr(account, "api_key", "") or "")
        default_model = str(getattr(account, "default_model", "") or "")
        return {
            "id": account.id,
            "name": account.name,
            "provider_type": account.provider_type,
            "base_url": account.base_url,
            "baseUrl": account.base_url,
            "default_model": default_model,
            "defaultModel": default_model,
            "model": default_model,
            "api_key_configured": bool(api_key),
            "apiKeyConfigured": bool(api_key),
            "api_key_masked": cls._mask_api_key(api_key),
            "apiKeyMasked": cls._mask_api_key(api_key),
            "status": "enabled" if account.enabled else "disabled",
            "enabled": account.enabled,
            "created_at": account.created_at.isoformat() if account.created_at is not None else None,
        }

    def _serialize_route(self, route) -> dict:
        account = self._provider_repo.get_provider(route.provider_account_id)
        return {
            "id": route.id,
            "provider_account_id": route.provider_account_id,
            "providerAccountId": route.provider_account_id,
            "provider_name": account.name if account is not None else "",
            "providerName": account.name if account is not None else "",
            "model": route.model,
            "priority": route.priority,
            "enabled": route.enabled,
        }

    def _ensure_initial_routes(self) -> None:
        if self._provider_repo is None or self._provider_repo.has_routes():
            return
        entries = [
            {"provider_account_id": account.id, "model": account.default_model}
            for account in self._provider_repo.list_configured_openai_providers()
            if account.default_model
        ]
        if not entries:
            return
        for provider_group in PROVIDER_ROUTE_GROUPS:
            self._provider_repo.replace_routes(provider_group, entries)

    @staticmethod
    def _validate_provider_group(provider_group: str) -> None:
        if provider_group not in PROVIDER_ROUTE_GROUPS:
            raise ValueError(f"unsupported provider route group '{provider_group}'")

    @staticmethod
    def _mask_api_key(api_key: str) -> str:
        if not api_key:
            return ""
        return f"••••{api_key[-4:]}" if len(api_key) > 4 else "••••"

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
