import json

from app.application.ports.provider import PROVIDER_ROUTE_GROUPS, ProviderRegistry
from app.application.services.system_settings_registry import SETTINGS_REGISTRY, SettingsTab
from app.domain.repositories.system_settings_repo import SystemSettingsRepository, VersionedSetting


SOURCE_BUILD_AGENT_ENABLED = "source_build_agent_enabled"
INTERACTIVE_BROWSER_VERIFICATION_ENABLED = "interactive_browser_verification_enabled"
INTERACTIVE_BROWSER_AUTOMATIC_ENABLED = "interactive_browser_automatic_enabled"
INTERACTIVE_BROWSER_MAX_SESSIONS = "interactive_browser_max_sessions"
INTERACTIVE_BROWSER_SESSION_TIMEOUT_SECONDS = "interactive_browser_session_timeout_seconds"
NOVEL_SETTINGS_PREFIX = "novel_agent."
NOVEL_VECTOR_BACKENDS = {"disabled", "sqlite", "qdrant", "pgvector"}
NOVEL_TOOL_CATEGORIES = {"read", "propose", "operate"}

_NOVEL_DEFAULTS = {
    "vector_backend": "disabled",
    "endpoint": "",
    "collection_prefix": "novel",
    "dimension": 0,
    "embedding_model": "",
    "batch_size": 16,
    "threshold": 0.7,
    "concurrency": 2,
    "retries": 2,
    "cache_ttl": 3600,
    "enabled_tools": ["read"],
    "chapter_size": 12000,
    "index_policy": "incremental",
    "cost_budget_daily": 0.0,
    "cost_budget_per_request": 0.0,
    "api_key": "",
}


class SystemSettingsService:
    def __init__(
        self,
        repo: SystemSettingsRepository,
        provider_registry: ProviderRegistry,
        metrics_provider=None,
    ):
        self._repo = repo
        self._provider_registry = provider_registry
        self._metrics_provider = metrics_provider

    def get_source_build_agent_settings(self) -> dict:
        return {
            "enabled": self._repo.get_bool(SOURCE_BUILD_AGENT_ENABLED, default=False),
            "provider_configured": self._provider_available(),
        }

    def set_source_build_agent_enabled(self, enabled: bool) -> dict:
        self._repo.set_bool(SOURCE_BUILD_AGENT_ENABLED, enabled)
        return self.get_source_build_agent_settings()

    def get_section(self, domain: str, tab: str) -> dict:
        registered_tab = self._registered_tab(domain, tab)
        stored = self._repo.get_json(registered_tab.storage_key, registered_tab.normalize({}))
        return self._section_response(domain, tab, registered_tab.normalize(stored.value), stored)

    def save_section(
        self,
        domain: str,
        tab: str,
        value: dict[str, object],
        *,
        expected_version: str | None,
    ) -> dict:
        registered_tab = self._registered_tab(domain, tab)
        normalized = registered_tab.normalize(value)
        self._validate_section_value(domain, tab, normalized)
        stored = self._repo.put_json(registered_tab.storage_key, normalized, expected_version)
        return self._section_response(domain, tab, normalized, stored)

    def get_interactive_browser_settings(self) -> dict:
        return {
            "enabled": self._repo.get_bool(INTERACTIVE_BROWSER_VERIFICATION_ENABLED, default=False),
            "automatic_enabled": self._repo.get_bool(INTERACTIVE_BROWSER_AUTOMATIC_ENABLED, default=True),
            "max_sessions": self._clamp(self._repo.get_int(INTERACTIVE_BROWSER_MAX_SESSIONS, default=1), 1, 3),
            "session_timeout_seconds": self._clamp(
                self._repo.get_int(INTERACTIVE_BROWSER_SESSION_TIMEOUT_SECONDS, default=300), 60, 600
            ),
        }

    def set_interactive_browser_settings(
        self,
        *,
        enabled: bool,
        automatic_enabled: bool,
        max_sessions: int,
        session_timeout_seconds: int,
    ) -> dict:
        self._repo.set_bool(INTERACTIVE_BROWSER_VERIFICATION_ENABLED, enabled)
        self._repo.set_bool(INTERACTIVE_BROWSER_AUTOMATIC_ENABLED, automatic_enabled)
        self._repo.set_int(INTERACTIVE_BROWSER_MAX_SESSIONS, self._clamp(max_sessions, 1, 3))
        self._repo.set_int(
            INTERACTIVE_BROWSER_SESSION_TIMEOUT_SECONDS,
            self._clamp(session_timeout_seconds, 60, 600),
        )
        return self.get_interactive_browser_settings()

    def get_novel_settings(self, *, include_secrets: bool = False) -> dict:
        """Return novel-agent settings, with credentials hidden by default."""
        raw = self._read_novel_settings()
        if include_secrets:
            return raw
        return self._safe_novel_settings(raw)

    def set_novel_settings(self, values: dict | None = None, **updates) -> dict:
        """Validate and persist the vector/embedding settings surface."""
        incoming = dict(values or {})
        incoming.update(updates)
        if "backend" in incoming and "vector_backend" not in incoming:
            incoming["vector_backend"] = incoming["backend"]

        current = self._read_novel_settings()
        for key in _NOVEL_DEFAULTS:
            if key in incoming and incoming[key] is not None:
                current[key] = incoming[key]
        current["vector_backend"] = str(current["vector_backend"] or "disabled").strip().lower()
        current["endpoint"] = str(current["endpoint"] or "").strip()
        current["collection_prefix"] = str(current["collection_prefix"] or "novel").strip()
        current["embedding_model"] = str(current["embedding_model"] or "").strip()
        current["api_key"] = str(current.get("api_key") or "")
        current["enabled_tools"] = self._normalize_tools(current.get("enabled_tools"))
        self._validate_novel_settings(current)

        for key, value in current.items():
            self._write_value(
                f"{NOVEL_SETTINGS_PREFIX}{key}",
                json.dumps(value, ensure_ascii=False) if key == "enabled_tools" else str(value),
            )
        return self._safe_novel_settings(current)

    # Alias used by callers that model settings updates as an HTTP-style
    # operation rather than a setter.
    update_novel_settings = set_novel_settings

    @staticmethod
    async def check_vector_store(vector_store) -> dict:
        return await vector_store.health()

    def _read_novel_settings(self) -> dict:
        result = dict(_NOVEL_DEFAULTS)
        for key, default in _NOVEL_DEFAULTS.items():
            value = self._read_value(f"{NOVEL_SETTINGS_PREFIX}{key}", None)
            if value is None:
                continue
            if key == "enabled_tools":
                try:
                    result[key] = json.loads(value)
                except (TypeError, json.JSONDecodeError):
                    result[key] = default
            elif key in {
                "dimension",
                "batch_size",
                "concurrency",
                "retries",
                "cache_ttl",
                "chapter_size",
            }:
                try:
                    result[key] = int(value)
                except (TypeError, ValueError):
                    result[key] = default
            elif key in {"threshold", "cost_budget_daily", "cost_budget_per_request"}:
                try:
                    result[key] = float(value)
                except (TypeError, ValueError):
                    result[key] = default
            else:
                result[key] = value
        return result

    def _safe_novel_settings(self, raw: dict) -> dict:
        api_key = str(raw.get("api_key") or "")
        backend = str(raw.get("vector_backend") or "disabled")
        safe = {key: value for key, value in raw.items() if key != "api_key"}
        route_groups = self._route_groups()
        safe.update(
            {
                "backend": backend,
                "credential_configured": bool(api_key),
                "credential_masked": self._mask_secret(api_key),
                "route_groups": route_groups,
                "provider_groups": list(route_groups),
                "models": {
                    group: sorted({entry["model"] for entry in entries if entry.get("model")})
                    for group, entries in route_groups.items()
                },
                "agent_permissions": {
                    category: category in set(raw.get("enabled_tools") or [])
                    for category in sorted(NOVEL_TOOL_CATEGORIES)
                },
                "index_policy": {
                    "mode": str(raw.get("index_policy") or "incremental"),
                    "chapter_size": int(raw.get("chapter_size") or 12000),
                    "concurrency": int(raw.get("concurrency") or 2),
                    "retries": int(raw.get("retries") or 2),
                },
                "cost_budget": {
                    "daily": float(raw.get("cost_budget_daily") or 0.0),
                    "per_request": float(raw.get("cost_budget_per_request") or 0.0),
                },
                "metrics": self._usage_metrics(),
            }
        )
        return safe

    def _usage_metrics(self) -> dict:
        empty = {
            "requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost": 0.0,
            "evidence_count": 0,
            "providers": [],
            "models": {"novel_chat": []},
        }
        if self._metrics_provider is None:
            return empty
        try:
            runs = self._metrics_provider.list_runs(limit=1000)
        except Exception:
            return empty
        providers: set[str] = set()
        models: set[str] = set()
        metrics = dict(empty)
        for run in runs or []:
            if getattr(run, "agent_kind", "novel") != "novel":
                continue
            metadata = getattr(run, "request_metadata", {}) or {}
            if not metadata.get("provider") and not metadata.get("model") and not metadata.get("usage"):
                continue
            metrics["requests"] += 1
            if metadata.get("cache_hit"):
                metrics["cache_hits"] += 1
            else:
                metrics["cache_misses"] += 1
            usage = metadata.get("usage") if isinstance(metadata.get("usage"), dict) else {}
            metrics["input_tokens"] += int(usage.get("input_tokens") or 0)
            metrics["output_tokens"] += int(usage.get("output_tokens") or 0)
            metrics["cost"] += float(metadata.get("cost") or 0.0)
            evidence_ids = metadata.get("evidence_ids") or []
            metrics["evidence_count"] += len(evidence_ids) if isinstance(evidence_ids, list) else 0
            if metadata.get("provider"):
                providers.add(str(metadata["provider"]))
            if metadata.get("model"):
                models.add(str(metadata["model"]))
        metrics["cost"] = round(metrics["cost"], 8)
        metrics["providers"] = sorted(providers)
        metrics["models"] = {"novel_chat": sorted(models)}
        return metrics

    def _route_groups(self) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = {}
        for group in PROVIDER_ROUTE_GROUPS:
            try:
                selections = self._provider_registry.resolve_group(group)
            except LookupError:
                selections = []
            entries = []
            for selection in selections:
                provider = getattr(selection, "provider", selection)
                model = getattr(selection, "model", "")
                provider_name = getattr(provider, "name", "")
                if isinstance(selection, dict):
                    model = selection.get("model", model)
                    provider_name = selection.get("provider", provider_name)
                entries.append(
                    {
                        "provider": str(provider_name or ""),
                        "model": str(model or ""),
                        "enabled": True,
                    }
                )
            groups[group] = entries
        return groups

    def _read_value(self, key: str, default):
        getter = getattr(self._repo, "get_value", None)
        if callable(getter):
            try:
                return getter(key, default)
            except NotImplementedError:
                pass
        getter = getattr(self._repo, "get", None)
        if callable(getter):
            return getter(key, default)
        return default

    def _write_value(self, key: str, value: str) -> None:
        setter = getattr(self._repo, "set_value", None)
        if callable(setter):
            try:
                setter(key, value)
                return
            except NotImplementedError:
                pass
        setter = getattr(self._repo, "set", None)
        if callable(setter):
            setter(key, value)
            return
        raise RuntimeError("system settings repository does not support generic values")

    @staticmethod
    def _normalize_tools(value) -> list[str]:
        if value is None:
            return ["read"]
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            raise ValueError("enabled_tools must be a list")
        tools = sorted({str(item).strip().lower() for item in value if str(item).strip()})
        if not tools:
            return ["read"]
        if not set(tools).issubset(NOVEL_TOOL_CATEGORIES):
            raise ValueError("enabled_tools contains an unsupported category")
        return tools

    @staticmethod
    def _validate_novel_settings(values: dict) -> None:
        backend = values["vector_backend"]
        if backend not in NOVEL_VECTOR_BACKENDS:
            raise ValueError("vector_backend must be disabled, sqlite, qdrant or pgvector")
        endpoint = values["endpoint"]
        if backend in {"qdrant", "pgvector"} and not endpoint:
            raise ValueError(f"endpoint is required for {backend}")
        if backend == "qdrant" and not endpoint.startswith(("http://", "https://")):
            raise ValueError("qdrant endpoint must use http or https")
        if not 0 <= int(values["dimension"]) <= 65536:
            raise ValueError("dimension must be between 0 and 65536")
        if not 1 <= int(values["batch_size"]) <= 256:
            raise ValueError("batch_size must be between 1 and 256")
        if not 0 <= float(values["threshold"]) <= 1:
            raise ValueError("threshold must be between 0 and 1")
        if not 1 <= int(values["concurrency"]) <= 64:
            raise ValueError("concurrency must be between 1 and 64")
        if not 0 <= int(values["retries"]) <= 10:
            raise ValueError("retries must be between 0 and 10")
        if not 0 <= int(values["cache_ttl"]):
            raise ValueError("cache_ttl must be non-negative")
        if not 1000 <= int(values["chapter_size"]) <= 100000:
            raise ValueError("chapter_size must be between 1000 and 100000")
        if str(values["index_policy"]) not in {"incremental", "full"}:
            raise ValueError("index_policy must be incremental or full")
        if float(values["cost_budget_daily"]) < 0 or float(values["cost_budget_per_request"]) < 0:
            raise ValueError("cost budgets must be non-negative")
        if not values["collection_prefix"] or len(values["collection_prefix"]) > 80:
            raise ValueError("collection_prefix must be between 1 and 80 characters")

    @staticmethod
    def _mask_secret(value: str) -> str:
        if not value:
            return ""
        return f"••••{value[-4:]}" if len(value) > 4 else "••••"

    def _provider_available(self) -> bool:
        try:
            return bool(self._provider_registry.resolve_group("source_build"))
        except LookupError:
            return False

    @staticmethod
    def _clamp(value: int, lower: int, upper: int) -> int:
        return min(max(int(value), lower), upper)

    @staticmethod
    def _registered_tab(domain: str, tab: str) -> SettingsTab:
        registered_tab = SETTINGS_REGISTRY.get_tab(domain, tab)
        if registered_tab is None:
            raise ValueError(f"Unknown settings section: {domain}/{tab}")
        return registered_tab

    @staticmethod
    def _section_response(
        domain: str,
        tab: str,
        value: dict[str, object],
        stored: VersionedSetting,
    ) -> dict:
        return {
            "domain": domain,
            "tab": tab,
            "value": value,
            "version": stored.version,
            "updated_at": stored.updated_at.isoformat() if stored.updated_at else None,
        }

    @staticmethod
    def _validate_section_value(domain: str, tab: str, value: dict[str, object]) -> None:
        if (domain, tab) != ("agents", "roles"):
            return
        unsupported = sorted(
            route_group
            for route_group in value.values()
            if route_group not in PROVIDER_ROUTE_GROUPS
        )
        if unsupported:
            raise ValueError("unsupported provider route group(s): " + ", ".join(unsupported))
