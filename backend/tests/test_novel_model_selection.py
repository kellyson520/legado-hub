import pytest


class FakePreferences:
    values = {
        ("user:1", "conversation", "c1", "chat"): "session",
        ("user:1", "book", "9", "chat"): "book",
        ("user:1", "user", "1", "chat"): "user",
    }

    def get(self, owner_scope, scope_type, scope_id, task_type):
        return self.values.get((owner_scope, scope_type, str(scope_id), task_type))


class FakeRoutes:
    def default_model(self, owner_scope, task_type):
        return "route"


def test_model_precedence_is_request_then_session_then_book_then_user_then_route():
    from app.application.services.novel_model_selection_service import NovelModelSelectionService

    resolver = NovelModelSelectionService(preferences=FakePreferences(), routes=FakeRoutes())
    assert resolver.resolve("user:1", 9, "c1", "chat", "request") == "request"
    assert resolver.resolve("user:1", 9, "c1", "chat", None) == "session"
    assert resolver.resolve("user:1", 9, None, "chat", None) == "book"
    assert resolver.resolve("user:1", None, None, "chat", None) == "user"
    assert resolver.resolve("user:2", 9, None, "chat", None) == "route"


def test_model_selection_rejects_disabled_request_model():
    from app.application.services.novel_model_selection_service import (
        NovelModelSelectionService,
        NovelModelUnavailable,
    )

    resolver = NovelModelSelectionService(
        preferences=FakePreferences(), routes=FakeRoutes(), available_models={"chat": {"route"}}
    )
    with pytest.raises(NovelModelUnavailable):
        resolver.resolve("user:1", None, None, "chat", "disabled")
