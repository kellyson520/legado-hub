def build_repository(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "settings-registry.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.system_settings_repo_impl import (
        SQLiteSystemSettingsRepository,
    )

    bootstrap_sqlite()
    return SQLiteSystemSettingsRepository()


def test_agent_governance_normalizer_returns_bounded_defaults():
    from app.application.services.system_settings_registry import normalize_agent_governance

    value = normalize_agent_governance(
        {
            "minimum_inferred_evidence": 1,
        }
    )

    assert value["automatic_publish_explicit"] is True
    assert value["automatic_publish_inferred"] is False
    assert value["minimum_inferred_evidence"] == 2


def test_agent_budget_normalizer_returns_bounded_defaults():
    from app.application.services.system_settings_registry import normalize_agent_budgets

    value = normalize_agent_budgets(
        {
            "max_tool_calls_per_task": 999,
            "max_chapters_per_task": 0,
            "max_concurrent_tasks": 99,
        }
    )

    assert value["max_tool_calls_per_task"] == 100
    assert value["max_chapters_per_task"] == 1
    assert value["max_concurrent_tasks"] == 8


def test_agent_settings_registry_lists_governance_tabs():
    from app.application.services.system_settings_registry import SETTINGS_REGISTRY

    tabs = SETTINGS_REGISTRY.tabs_for_domain("agents")

    assert [tab.id for tab in tabs] == [
        "overview",
        "roles",
        "automation",
        "governance",
        "budgets",
        "audit",
    ]


def test_system_settings_service_saves_a_registered_section(monkeypatch, tmp_path):
    from app.application.services.system_settings_service import SystemSettingsService

    repository = build_repository(monkeypatch, tmp_path)

    class ProviderRegistry:
        def resolve_group(self, _group):
            return [object()]

    service = SystemSettingsService(repository, ProviderRegistry())

    initial = service.get_section("agents", "budgets")
    saved = service.save_section(
        "agents",
        "budgets",
        {"max_tool_calls_per_task": 999},
        expected_version=initial["version"],
    )

    assert initial["value"]["max_tool_calls_per_task"] == 24
    assert saved["value"]["max_tool_calls_per_task"] == 100
    assert saved["version"] is not None
