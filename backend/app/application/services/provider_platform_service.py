import asyncio
import random
import re
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Protocol

from app.application.ports.provider import (
    PROVIDER_ROUTE_GROUPS,
    ProviderAdapter,
    ProviderRegistry,
    SUPPORTED_PROVIDER_TYPES,
    provider_http_status,
)
from app.core.redaction import sanitize_error


class ProviderQuotaLimiter(Protocol):
    def assert_allowed(self, quota_scope: tuple[str, str]) -> None:
        raise NotImplementedError


class ProviderInvocationError(RuntimeError):
    def __init__(self, provider_group: str, failures: list[str]):
        super().__init__(f"all providers failed for group '{provider_group}': {'; '.join(failures)}")
        self.provider_group = provider_group
        self.failures = failures


class ProviderQuotaExceeded(RuntimeError):
    code = "provider_quota_exceeded"


class RepositoryProviderQuotaLimiter:
    """Enforce repository-backed daily cost policies in the process boundary."""

    def __init__(self, provider_repo, *, clock=None):
        self._provider_repo = provider_repo
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._usage: dict[tuple[str, str, str], float] = defaultdict(float)
        self._reservations: dict[tuple[str, str, str], int] = defaultdict(int)
        self._lock = Lock()

    def assert_allowed(self, quota_scope: tuple[str, str]) -> None:
        policy = self._policy(quota_scope)
        if policy is None:
            return
        limit = float(getattr(policy, "daily_cost_limit", 0.0) or 0.0)
        if limit <= 0:
            return
        key = (*quota_scope, self._date_key())
        with self._lock:
            current = self._usage[key]
            if current >= limit or self._reservations[key] > 0:
                raise ProviderQuotaExceeded("provider daily cost quota exceeded")
            self._reservations[key] += 1

    def record_usage(self, quota_scope: tuple[str, str], cost: float = 0.0) -> None:
        amount = max(0.0, float(cost or 0.0))
        if amount <= 0:
            return
        policy = self._policy(quota_scope)
        if policy is None:
            return
        key = (*quota_scope, self._date_key())
        with self._lock:
            self._usage[key] += amount

    def release_reservation(self, quota_scope: tuple[str, str]) -> None:
        """Release the in-flight request slot after success or failure."""

        key = (*quota_scope, self._date_key())
        with self._lock:
            if self._reservations[key] > 0:
                self._reservations[key] -= 1

    def _policy(self, quota_scope: tuple[str, str]):
        try:
            policies = self._provider_repo.list_quota_policies()
        except Exception as exc:
            raise RuntimeError("provider quota policy unavailable") from exc
        scope_type, scope_id = quota_scope
        exact = next(
            (
                item for item in policies or []
                if str(getattr(item, "scope_type", "")) == str(scope_type)
                and str(getattr(item, "scope_id", "")) == str(scope_id)
            ),
            None,
        )
        return exact or next(
            (
                item for item in policies or []
                if str(getattr(item, "scope_type", "")) in {"global", "*"}
                and str(getattr(item, "scope_id", "")) in {"", "*"}
            ),
            None,
        )

    def _date_key(self) -> str:
        return self._clock().date().isoformat()


class ProviderPlatformService:
    def __init__(
        self,
        registry: ProviderRegistry,
        quota_limiter: ProviderQuotaLimiter,
        provider_repo=None,
        provider_factory=None,
        *,
        max_retries: int = 2,
        retry_base_delay: float = 0.25,
        retry_max_delay: float = 8.0,
        retry_jitter: float = 0.1,
    ):
        self._registry = registry
        self._quota_limiter = quota_limiter
        self._provider_repo = provider_repo
        self._provider_factory = provider_factory
        self._max_retries = max(0, min(int(max_retries), 5))
        self._retry_base_delay = max(0.0, float(retry_base_delay))
        self._retry_max_delay = max(self._retry_base_delay, float(retry_max_delay))
        self._retry_jitter = max(0.0, min(float(retry_jitter), 1.0))

    async def invoke_chat(
        self,
        provider_group: str,
        model: str | None,
        payload: dict[str, Any],
        quota_scope: tuple[str, str],
    ) -> dict[str, Any]:
        self._quota_limiter.assert_allowed(quota_scope)
        try:
            selections = self._registry.resolve_group(provider_group)
            failures: list[str] = []
            requested_model = (model or "").strip()
            use_route_model = not requested_model

            for attempt_count, selection in enumerate(selections, start=1):
                candidate_model = selection.model if use_route_model else requested_model
                if not candidate_model:
                    raise LookupError(f"no model configured for provider route group '{provider_group}'")
                for retry_index in range(self._max_retries + 1):
                    try:
                        result = await selection.provider.invoke_chat(model=candidate_model, payload=payload)
                        normalized = self._normalize_result(
                            result=result,
                            provider=selection.provider,
                            provider_group=provider_group,
                            model=candidate_model,
                            attempt_count=attempt_count,
                        )
                        self._record_quota_usage(quota_scope, normalized)
                        return normalized
                    except Exception as exc:
                        if self._is_non_retryable_request_error(exc):
                            raise
                        if retry_index < self._max_retries and self._is_retryable_provider_error(exc):
                            await self._backoff(retry_index)
                            continue
                        failures.append(self._sanitize_provider_failure(selection.provider.name, exc))
                        if requested_model and self._is_model_not_found_error(exc):
                            use_route_model = True
                        break

            raise ProviderInvocationError(provider_group, failures)
        finally:
            self._release_quota_reservation(quota_scope)

    async def invoke_novel_chat(
        self,
        *,
        owner_scope: str,
        model: str | None,
        payload: dict[str, Any],
        quota_scope: tuple[str, str],
    ) -> dict[str, Any]:
        return await self._invoke_specialized("novel_chat", "invoke_chat", owner_scope, model, payload, quota_scope)

    async def invoke_novel_extract(
        self,
        *,
        owner_scope: str,
        model: str | None,
        payload: dict[str, Any],
        quota_scope: tuple[str, str],
    ) -> dict[str, Any]:
        return await self._invoke_specialized("novel_extract", "invoke_chat", owner_scope, model, payload, quota_scope)

    async def invoke_novel_summary(
        self,
        *,
        owner_scope: str,
        model: str | None,
        payload: dict[str, Any],
        quota_scope: tuple[str, str],
    ) -> dict[str, Any]:
        return await self._invoke_specialized("novel_summary", "invoke_chat", owner_scope, model, payload, quota_scope)

    async def invoke_novel_embedding(
        self,
        *,
        owner_scope: str,
        model: str | None,
        payload: dict[str, Any],
        quota_scope: tuple[str, str],
    ) -> dict[str, Any]:
        return await self._invoke_specialized("novel_embedding", "invoke_embedding", owner_scope, model, payload, quota_scope)

    async def _invoke_specialized(
        self,
        provider_group: str,
        method_name: str,
        owner_scope: str,
        model: str | None,
        payload: dict[str, Any],
        quota_scope: tuple[str, str],
    ) -> dict[str, Any]:
        self._quota_limiter.assert_allowed(quota_scope)
        try:
            selections = self._registry.resolve_group(provider_group)
            requested_model = (model or "").strip()
            use_route_model = not requested_model
            failures: list[str] = []
            for attempt_count, selection in enumerate(selections, start=1):
                candidate_model = selection.model if use_route_model else requested_model
                if not candidate_model:
                    raise LookupError(f"no model configured for provider route group '{provider_group}'")
                for retry_index in range(self._max_retries + 1):
                    try:
                        method = getattr(selection.provider, method_name)
                        result = await method(model=candidate_model, payload=payload)
                        normalized = self._normalize_result(
                            result=result,
                            provider=selection.provider,
                            provider_group=provider_group,
                            model=candidate_model,
                            attempt_count=attempt_count,
                        )
                        normalized["owner_scope"] = owner_scope
                        self._record_quota_usage(quota_scope, normalized)
                        return normalized
                    except Exception as exc:
                        if self._is_non_retryable_request_error(exc):
                            raise
                        if retry_index < self._max_retries and self._is_retryable_provider_error(exc):
                            await self._backoff(retry_index)
                            continue
                        failures.append(self._sanitize_provider_failure(selection.provider.name, exc))
                        if requested_model and self._is_model_not_found_error(exc):
                            use_route_model = True
                        break
            raise ProviderInvocationError(provider_group, failures)
        finally:
            self._release_quota_reservation(quota_scope)

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
        provider_type: str | None = None,
        activation_at: datetime | None = None,
        provider_id: str | None = None,
    ) -> dict:
        if self._provider_repo is None:
            raise RuntimeError("provider repository is not configured")
        existing_account = None
        if provider_id is not None:
            existing_account = self._provider_repo.get_provider(provider_id)
            if existing_account is None:
                raise LookupError("provider not found")
        provider_type = str(
            provider_type or getattr(existing_account, "provider_type", "") or "openai_compatible"
        ).strip()
        if provider_type not in SUPPORTED_PROVIDER_TYPES:
            raise ValueError(f"unsupported provider type: {provider_type}")
        account = self._provider_repo.save_provider(
            id=provider_id,
            name=name,
            base_url=base_url,
            api_key=api_key,
            default_model=default_model,
            enabled=enabled,
            provider_type=provider_type,
            activation_at=activation_at,
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
        if self._provider_factory is None:
            raise RuntimeError("provider factory is not configured")
        provider = self._provider_factory(
            account.name,
            account.base_url,
            account.api_key,
            provider_type=account.provider_type,
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
        if not any(entry["enabled"] for entry in normalized_entries):
            raise ValueError("at least one provider route entry must be enabled")
        routes = self._provider_repo.replace_routes(provider_group, normalized_entries)
        return {"group": provider_group, "entries": [self._serialize_route(route) for route in routes]}

    def get_llm_settings(self, default_provider_name: str, default_model: str) -> dict:
        account = self._legacy_llm_account()
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
        existing = self._legacy_llm_account()
        account = self._provider_repo.save_provider(
            id=existing.id if existing is not None else None,
            name=provider_name,
            base_url=base_url,
            api_key=api_key,
            default_model=model,
            enabled=True,
        )
        self._ensure_initial_routes()
        self._sync_legacy_route_models(account.id, model)
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
        activation_at = getattr(account, "activation_at", None)
        if activation_at is not None and activation_at.tzinfo is None:
            activation_at = activation_at.replace(tzinfo=timezone.utc)
        scheduled = bool(activation_at is not None and activation_at > datetime.now(timezone.utc))
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
            "status": "scheduled" if account.enabled and scheduled else ("enabled" if account.enabled else "disabled"),
            "enabled": account.enabled,
            "activation_at": activation_at.isoformat() if activation_at is not None else None,
            "activationAt": activation_at.isoformat() if activation_at is not None else None,
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
            for account in self._provider_repo.list_configured_providers()
            if account.default_model
        ]
        if not entries:
            return
        for provider_group in PROVIDER_ROUTE_GROUPS:
            self._provider_repo.replace_routes(provider_group, entries)

    def _legacy_llm_account(self):
        if self._provider_repo is None:
            return None
        default_routes = self._provider_repo.list_routes("default")
        if default_routes:
            account = self._provider_repo.get_provider(default_routes[0].provider_account_id)
            if account is not None and account.is_active():
                return account
        account = self._provider_repo.get_llm_provider()
        return account if account is not None and account.is_active() else None

    def _sync_legacy_route_models(self, provider_id: str, model: str) -> None:
        if self._provider_repo is None:
            return
        for provider_group in PROVIDER_ROUTE_GROUPS:
            routes = self._provider_repo.list_routes(provider_group)
            if not any(route.provider_account_id == provider_id for route in routes):
                continue
            self._provider_repo.replace_routes(
                provider_group,
                [
                    {
                        "provider_account_id": route.provider_account_id,
                        "model": model if route.provider_account_id == provider_id else route.model,
                        "enabled": route.enabled,
                    }
                    for route in routes
                ],
            )

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
    def _is_non_retryable_request_error(exc: Exception) -> bool:
        return provider_http_status(exc) in {400, 401, 403, 422}

    @staticmethod
    def _is_retryable_provider_error(exc: Exception) -> bool:
        status = provider_http_status(exc)
        if status is not None:
            return status in {408, 409, 425, 429, 500, 502, 503, 504}
        return isinstance(exc, (ConnectionError, TimeoutError, OSError, RuntimeError))

    async def _backoff(self, retry_index: int) -> None:
        delay = min(self._retry_max_delay, self._retry_base_delay * (2 ** retry_index))
        if self._retry_jitter:
            delay += random.uniform(0.0, delay * self._retry_jitter)
        await asyncio.sleep(delay)

    def _record_quota_usage(self, quota_scope: tuple[str, str], result: dict[str, Any]) -> None:
        recorder = getattr(self._quota_limiter, "record_usage", None)
        if not callable(recorder):
            return
        cost = result.get("cost", 0.0) if isinstance(result, dict) else 0.0
        if isinstance(cost, dict):
            cost = cost.get("total", cost.get("amount", 0.0))
        recorder(quota_scope, float(cost or 0.0))

    def _release_quota_reservation(self, quota_scope: tuple[str, str]) -> None:
        releaser = getattr(self._quota_limiter, "release_reservation", None)
        if callable(releaser):
            releaser(quota_scope)

    @staticmethod
    def _is_model_not_found_error(exc: Exception) -> bool:
        return provider_http_status(exc) == 404

    @staticmethod
    def _sanitize_provider_failure(provider_name: str, exc: Exception) -> str:
        message = sanitize_error(exc, limit=240)
        message = re.sub(
            r"(?i)authorization=\[redacted\]",
            "Authorization: Bearer [redacted]",
            message,
        )
        return f"{provider_name}: {message}"

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
