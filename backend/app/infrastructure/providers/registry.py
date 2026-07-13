from collections.abc import Mapping

from .base import ProviderAdapter


class ProviderRegistry:
    def __init__(self, providers_by_group: Mapping[str, list[ProviderAdapter]] | None = None):
        self._providers_by_group = {
            group: list(providers)
            for group, providers in (providers_by_group or {}).items()
        }

    def resolve_group(self, provider_group: str) -> list[ProviderAdapter]:
        providers = self._providers_by_group.get(provider_group, [])
        if not providers:
            raise LookupError(f"no providers registered for group '{provider_group}'")
        return list(providers)

    def register_group(self, provider_group: str, providers: list[ProviderAdapter]) -> None:
        self._providers_by_group[provider_group] = list(providers)

    def snapshot(self) -> dict[str, list[ProviderAdapter]]:
        return {
            group: list(providers)
            for group, providers in self._providers_by_group.items()
        }
