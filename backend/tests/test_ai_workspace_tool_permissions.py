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


def test_workspace_joint_test_requires_source_permissions_and_agent_provider(monkeypatch):
    import app.interfaces.http.ai as ai_router

    monkeypatch.setattr(
        ai_router,
        "build_system_settings_service",
        lambda: SettingsService({"enabled": True, "provider_configured": True}),
    )

    names = ai_router._workspace_tool_names(Identity({"ai.run", "book_sources.read", "book_sources.write"}))

    assert "source.joint_test" in names


def test_workspace_joint_test_is_not_granted_without_source_write(monkeypatch):
    import app.interfaces.http.ai as ai_router

    monkeypatch.setattr(
        ai_router,
        "build_system_settings_service",
        lambda: SettingsService({"enabled": True, "provider_configured": True}),
    )

    names = ai_router._workspace_tool_names(Identity({"ai.run", "book_sources.read"}))

    assert "source.joint_test" not in names


def test_workspace_content_reading_tools_require_source_read_permission(monkeypatch):
    import app.interfaces.http.ai as ai_router

    monkeypatch.setattr(
        ai_router,
        "build_system_settings_service",
        lambda: SettingsService({"enabled": False, "provider_configured": False}),
    )

    names = ai_router._workspace_tool_names(Identity({"ai.run", "book_sources.read"}))

    assert {"source.search", "toc.get", "chapter.fetch"} <= names


def test_workspace_content_reading_tools_are_not_granted_without_source_read_permission(monkeypatch):
    import app.interfaces.http.ai as ai_router

    monkeypatch.setattr(
        ai_router,
        "build_system_settings_service",
        lambda: SettingsService({"enabled": False, "provider_configured": False}),
    )

    names = ai_router._workspace_tool_names(Identity({"ai.run"}))

    assert not ({"source.search", "toc.get", "chapter.fetch"} & names)
