import json

from app.domain.repositories.system_settings_repo import SystemSettingsRepository
from app.infrastructure.providers.registry import ProviderRegistry


SOURCE_BUILD_AGENT_ENABLED = "source_build_agent_enabled"
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
    "api_key": "",
}


class SystemSettingsService:
    def __init__(self, repo: SystemSettingsRepository, provider_registry: ProviderRegistry):
        self._repo = repo
        self._provider_registry = provider_registry

    def get_source_build_agent_settings(self) -> dict:
        return {
            "enabled": self._repo.get_bool(SOURCE_BUILD_AGENT_ENABLED, default=False),
            "provider_configured": self._provider_available(),
        }

    def set_source_build_agent_enabled(self, enabled: bool) -> dict:
        self._repo.set_bool(SOURCE_BUILD_AGENT_ENABLED, enabled)
        return self.get_source_build_agent_settings()

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
            elif key in {"dimension", "batch_size", "concurrency", "retries", "cache_ttl"}:
                try:
                    result[key] = int(value)
                except (TypeError, ValueError):
                    result[key] = default
            elif key == "threshold":
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
        safe.update(
            {
                "backend": backend,
                "credential_configured": bool(api_key),
                "credential_masked": self._mask_secret(api_key),
            }
        )
        return safe

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
