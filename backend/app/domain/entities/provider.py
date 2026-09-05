from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ProviderAccount:
    id: str = ""
    name: str = ""
    provider_type: str = ""
    base_url: str = ""
    api_key: str = ""
    default_model: str = ""
    enabled: bool = True
    activation_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)

    def is_active(self, now: datetime | None = None) -> bool:
        if not self.enabled:
            return False
        if self.activation_at is None:
            return True
        current = now or utcnow()
        activation_at = self.activation_at
        if activation_at.tzinfo is None:
            activation_at = activation_at.replace(tzinfo=timezone.utc)
        return activation_at <= current


@dataclass
class ProviderRoute:
    id: str = ""
    provider_group: str = ""
    provider_account_id: str = ""
    model: str = ""
    priority: int = 0
    enabled: bool = True


@dataclass
class ProviderModel:
    id: str = ""
    provider_account_id: str = ""
    name: str = ""
    capabilities: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class QuotaPolicy:
    id: str = ""
    scope_type: str = ""
    scope_id: str = ""
    daily_cost_limit: float = 0.0
    created_at: datetime = field(default_factory=utcnow)
