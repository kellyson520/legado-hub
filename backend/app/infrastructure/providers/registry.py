from collections.abc import Mapping
from dataclasses import dataclass

from .base import ProviderAdapter


@dataclass(frozen=True)
class ProviderSelection:
    provider: ProviderAdapter
    model: str = ""

    @property
    def name(self) -> str:
        return self.provider.name


class ProviderRegistry:
    def __init__(
        self,
        providers_by_group: Mapping[str, list[ProviderAdapter | ProviderSelection]] | None = None,
    ):
        self._providers_by_group = {
            group: [self._as_selection(provider) for provider in providers]
            for group, providers in (providers_by_group or {}).items()
        }

    @staticmethod
    def _as_selection(provider: ProviderAdapter | ProviderSelection) -> ProviderSelection:
        return provider if isinstance(provider, ProviderSelection) else ProviderSelection(provider)

    def resolve_group(self, provider_group: str) -> list[ProviderSelection]:
        providers = self._providers_by_group.get(provider_group, [])
        if not providers:
            raise LookupError(f"no providers registered for group '{provider_group}'")
        return list(providers)

    def register_group(self, provider_group: str, providers: list[ProviderAdapter | ProviderSelection]) -> None:
        self._providers_by_group[provider_group] = [self._as_selection(provider) for provider in providers]

    def snapshot(self) -> dict[str, list[ProviderSelection]]:
        return {
            group: list(providers)
            for group, providers in self._providers_by_group.items()
        }
