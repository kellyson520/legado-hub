from abc import ABC, abstractmethod

from datetime import datetime

from app.domain.entities.provider import ProviderAccount, ProviderModel, ProviderRoute, QuotaPolicy


class ProviderRepository(ABC):
    @abstractmethod
    def create_provider_account(self, name: str, provider_type: str, base_url: str) -> ProviderAccount:
        raise NotImplementedError

    @abstractmethod
    def upsert_llm_provider(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
    ) -> ProviderAccount:
        raise NotImplementedError

    @abstractmethod
    def save_provider(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
        enabled: bool,
        activation_at: datetime | None = None,
        id: str | None = None,
    ) -> ProviderAccount:
        raise NotImplementedError

    @abstractmethod
    def list_routes(self, provider_group: str) -> list[ProviderRoute]:
        raise NotImplementedError

    @abstractmethod
    def replace_routes(self, provider_group: str, entries: list[dict]) -> list[ProviderRoute]:
        raise NotImplementedError

    @abstractmethod
    def get_llm_provider(self) -> ProviderAccount | None:
        raise NotImplementedError

    @abstractmethod
    def create_model(self, provider_account_id: str, name: str, capabilities: list[str]) -> ProviderModel:
        raise NotImplementedError

    @abstractmethod
    def create_quota_policy(self, scope_type: str, scope_id: str, daily_cost_limit: float) -> QuotaPolicy:
        raise NotImplementedError

    @abstractmethod
    def list_provider_accounts(self) -> list[ProviderAccount]:
        raise NotImplementedError

    @abstractmethod
    def list_quota_policies(self) -> list[QuotaPolicy]:
        raise NotImplementedError
