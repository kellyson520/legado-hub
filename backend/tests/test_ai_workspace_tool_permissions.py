"""Workspace source operations require a complete operator capability grant."""


class Identity:
    def __init__(self, permissions):
        self.permissions = set(permissions)


class SettingsService:
    def __init__(self, settings):
        self._settings = settings

    def get_source_build_agent_settings(self):
        return self._settings


def test_workspace_candidate_draft_requires_source_read_and_write_permissions(monkeypatch):
    import app.interfaces.http.ai as ai_router

    monkeypatch.setattr(
        ai_router,
        "build_system_settings_service",
        lambda: SettingsService({"enabled": True, "provider_configured": True}),
    )

    names = ai_router._workspace_tool_names(Identity({"ai.run", "book_sources.write"}))

    assert "create_source_rule_draft" not in names


def test_workspace_candidate_draft_requires_a_configured_agent_provider(monkeypatch):
    import app.interfaces.http.ai as ai_router

    monkeypatch.setattr(
        ai_router,
        "build_system_settings_service",
        lambda: SettingsService({"enabled": True, "provider_configured": False}),
    )

    names = ai_router._workspace_tool_names(Identity({"ai.run", "book_sources.read", "book_sources.write"}))

    assert "create_source_rule_draft" not in names
