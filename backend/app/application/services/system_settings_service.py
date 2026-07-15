from app.domain.repositories.system_settings_repo import SystemSettingsRepository
from app.infrastructure.providers.registry import ProviderRegistry


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
