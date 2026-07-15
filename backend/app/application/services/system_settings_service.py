from app.domain.repositories.system_settings_repo import SystemSettingsRepository
from app.infrastructure.providers.registry import ProviderRegistry


SOURCE_BUILD_AGENT_ENABLED = "source_build_agent_enabled"


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

    def _provider_available(self) -> bool:
        try:
            return bool(self._provider_registry.resolve_group("source_build"))
        except LookupError:
            return False
