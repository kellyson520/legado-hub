from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


Normalizer = Callable[[dict[str, object]], dict[str, object]]


@dataclass(frozen=True)
class SettingsTab:
    domain: str
    id: str
    label: str
    default_value: dict[str, object] = field(default_factory=dict)
    normalizer: Normalizer | None = None

    @property
    def storage_key(self) -> str:
        return f"settings.{self.domain}.{self.id}"

    def normalize(self, value: dict[str, object]) -> dict[str, object]:
        merged = {**self.default_value, **value}
        return self.normalizer(merged) if self.normalizer else merged


@dataclass(frozen=True)
class SettingsDomain:
    id: str
    label: str
    tabs: tuple[SettingsTab, ...]


class SettingsRegistry:
    def __init__(self, domains: tuple[SettingsDomain, ...]):
        self._domains = {domain.id: domain for domain in domains}

    def tabs_for_domain(self, domain_id: str) -> tuple[SettingsTab, ...]:
        domain = self._domains.get(domain_id)
        return domain.tabs if domain else ()

    def get_tab(self, domain_id: str, tab_id: str) -> SettingsTab | None:
        return next(
            (tab for tab in self.tabs_for_domain(domain_id) if tab.id == tab_id),
            None,
        )


def _bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in {"true", "1", "yes", "on"}:
            return True
        if value.lower() in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, int):
        return bool(value)
    return default


def _bounded_int(value: object, default: int, lower: int, upper: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, lower), upper)


def normalize_agent_governance(value: dict[str, object]) -> dict[str, object]:
    return {
        "automatic_publish_explicit": _bool(value.get("automatic_publish_explicit"), True),
        "automatic_publish_inferred": _bool(value.get("automatic_publish_inferred"), False),
        "minimum_inferred_evidence": _bounded_int(
            value.get("minimum_inferred_evidence"), 2, 2, 8
        ),
        "require_human_review_for_identity": _bool(
            value.get("require_human_review_for_identity"), True
        ),
        "require_human_review_for_conflicts": _bool(
            value.get("require_human_review_for_conflicts"), True
        ),
    }


def normalize_agent_budgets(value: dict[str, object]) -> dict[str, object]:
    return {
        "max_chapters_per_task": _bounded_int(
            value.get("max_chapters_per_task"), 12, 1, 50
        ),
        "max_tool_calls_per_task": _bounded_int(
            value.get("max_tool_calls_per_task"), 24, 1, 100
        ),
        "max_tokens_per_task": _bounded_int(
            value.get("max_tokens_per_task"), 24000, 1000, 200000
        ),
        "max_concurrent_tasks": _bounded_int(
            value.get("max_concurrent_tasks"), 1, 1, 8
        ),
    }


def normalize_agent_automation(value: dict[str, object]) -> dict[str, object]:
    return {
        "enabled": _bool(value.get("enabled"), True),
        "background_incremental_enabled": _bool(
            value.get("background_incremental_enabled"), False
        ),
        "emergency_pause": _bool(value.get("emergency_pause"), False),
    }


def normalize_agent_roles(value: dict[str, object]) -> dict[str, object]:
    defaults = {
        "extractor_route_group": "novel_extract",
        "verifier_route_group": "novel_verify",
        "adjudicator_route_group": "novel_adjudicate",
        "auditor_route_group": "novel_audit",
    }
    return {
        key: str(value.get(key) or default).strip() or default
        for key, default in defaults.items()
    }


SETTINGS_REGISTRY = SettingsRegistry(
    domains=(
        SettingsDomain("general", "General", (SettingsTab("general", "preferences", "Preferences"),)),
        SettingsDomain("security", "Security and access", (SettingsTab("security", "access", "Access"),)),
        SettingsDomain("models", "Models and providers", (SettingsTab("models", "providers", "Providers"),)),
        SettingsDomain(
            "agents",
            "Agents and automation",
            (
                SettingsTab("agents", "overview", "Overview"),
                SettingsTab("agents", "roles", "Roles and models", normalizer=normalize_agent_roles),
                SettingsTab("agents", "automation", "Automation", normalizer=normalize_agent_automation),
                SettingsTab("agents", "governance", "Evidence and governance", normalizer=normalize_agent_governance),
                SettingsTab("agents", "budgets", "Budgets and queue", normalizer=normalize_agent_budgets),
                SettingsTab("agents", "audit", "Audit and tests"),
            ),
        ),
        SettingsDomain("sources", "Sources and browser", (SettingsTab("sources", "browser", "Browser verification"),)),
        SettingsDomain("storage", "Storage and maintenance", (SettingsTab("storage", "maintenance", "Maintenance"),)),
        SettingsDomain("runtime", "Runtime and observability", (SettingsTab("runtime", "observability", "Observability"),)),
    )
)
