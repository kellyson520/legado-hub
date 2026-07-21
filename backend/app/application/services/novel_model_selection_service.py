from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class NovelModelUnavailable(ValueError):
    code = "model_unavailable"


@dataclass(frozen=True)
class NovelModelResolution:
    model: str
    source: str
    provider_group: str


class NovelModelSelectionService:
    """Resolve request/session/book/user/route model precedence."""

    def __init__(self, *, preferences, routes, available_models: dict[str, set[str]] | None = None):
        self._preferences = preferences
        self._routes = routes
        self._available_models = available_models

    def resolve(
        self,
        owner_scope: str,
        book_id: int | None,
        conversation_id: str | None,
        task_type: str,
        request_model: str | None,
    ) -> str:
        return self.resolve_with_metadata(
            owner_scope, book_id, conversation_id, task_type, request_model
        ).model

    def resolve_with_metadata(
        self,
        owner_scope: str,
        book_id: int | None,
        conversation_id: str | None,
        task_type: str,
        request_model: str | None,
    ) -> NovelModelResolution:
        candidates: list[tuple[str, str | None]] = [
            ("request", request_model),
            ("session", self._preference(owner_scope, "conversation", conversation_id, task_type)),
            ("book", self._preference(owner_scope, "book", book_id, task_type)),
            ("user", self._preference(owner_scope, "user", self._user_id(owner_scope), task_type)),
        ]
        route_model = self._route_default(owner_scope, task_type)
        candidates.append(("route", route_model))
        for source, candidate in candidates:
            model = self._model_ref(candidate)
            if not model:
                continue
            self._validate(task_type, model)
            return NovelModelResolution(model=model, source=source, provider_group=self._group(task_type))
        raise NovelModelUnavailable(f"no model configured for novel task '{task_type}'")

    def _preference(self, owner_scope: str, scope_type: str, scope_id: Any, task_type: str):
        if scope_id is None:
            return None
        getter = getattr(self._preferences, "get", None)
        if not callable(getter):
            return None
        return getter(owner_scope, scope_type, str(scope_id), task_type)

    def _route_default(self, owner_scope: str, task_type: str):
        default_model = getattr(self._routes, "default_model", None)
        if callable(default_model):
            return default_model(owner_scope, task_type)
        resolver = getattr(self._routes, "resolve_group", None)
        if callable(resolver):
            selections = resolver(self._group(task_type))
            if selections:
                return getattr(selections[0], "model", None) or (
                    selections[0].get("model") if isinstance(selections[0], dict) else None
                )
        return None

    def _validate(self, task_type: str, model: str) -> None:
        if self._available_models is None:
            return
        available = self._available_models.get(task_type, set())
        if model not in available:
            raise NovelModelUnavailable(f"model '{model}' is not enabled for task '{task_type}'")

    @staticmethod
    def _model_ref(value) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return str(value.get("model_ref") or value.get("model") or "").strip()
        return str(getattr(value, "model_ref", "") or getattr(value, "model", "")).strip()

    @staticmethod
    def _user_id(owner_scope: str) -> str:
        return owner_scope.split(":", 1)[1] if ":" in owner_scope else owner_scope

    @staticmethod
    def _group(task_type: str) -> str:
        return {
            "chat": "novel_chat",
            "extract": "novel_extract",
            "summary": "novel_summary",
            "embedding": "novel_embedding",
        }.get(task_type, "novel")
