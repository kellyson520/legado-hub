from app.application.services.system_settings_registry import SETTINGS_REGISTRY, SettingsTab
from app.application.ports.provider import ProviderRegistry
from app.application.services.provider_platform_service import PROVIDER_ROUTE_GROUPS
from app.domain.repositories.system_settings_repo import SystemSettingsRepository, VersionedSetting


SOURCE_BUILD_AGENT_ENABLED = "source_build_agent_enabled"
INTERACTIVE_BROWSER_VERIFICATION_ENABLED = "interactive_browser_verification_enabled"
INTERACTIVE_BROWSER_AUTOMATIC_ENABLED = "interactive_browser_automatic_enabled"
INTERACTIVE_BROWSER_MAX_SESSIONS = "interactive_browser_max_sessions"
INTERACTIVE_BROWSER_SESSION_TIMEOUT_SECONDS = "interactive_browser_session_timeout_seconds"


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

    def get_section(self, domain: str, tab: str) -> dict:
        registered_tab = self._registered_tab(domain, tab)
        stored = self._repo.get_json(
            registered_tab.storage_key,
            registered_tab.normalize({}),
        )
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
        stored = self._repo.put_json(
            registered_tab.storage_key,
            normalized,
            expected_version,
        )
        return self._section_response(domain, tab, normalized, stored)

    def get_interactive_browser_settings(self) -> dict:
        return {
            'enabled': self._repo.get_bool(INTERACTIVE_BROWSER_VERIFICATION_ENABLED, default=False),
            'automatic_enabled': self._repo.get_bool(INTERACTIVE_BROWSER_AUTOMATIC_ENABLED, default=True),
            'max_sessions': self._clamp(
                self._repo.get_int(INTERACTIVE_BROWSER_MAX_SESSIONS, default=1), 1, 3,
            ),
            'session_timeout_seconds': self._clamp(
                self._repo.get_int(INTERACTIVE_BROWSER_SESSION_TIMEOUT_SECONDS, default=300), 60, 600,
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

    @staticmethod
    def _clamp(value: int, lower: int, upper: int) -> int:
        return min(max(int(value), lower), upper)

    def _provider_available(self) -> bool:
        try:
            return bool(self._provider_registry.resolve_group("source_build"))
        except LookupError:
            return False

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
            raise ValueError(
                "unsupported provider route group(s): " + ", ".join(unsupported)
            )
