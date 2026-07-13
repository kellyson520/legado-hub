from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from app.domain.entities.agent_runtime import ToolResult


ALLOWED_PATCH_FIELDS = frozenset({
    'searchUrl', 'header', 'ruleSearch', 'ruleBookInfo', 'ruleToc', 'ruleContent', 'replaceRule',
})


@dataclass
class SourceBuildToolContext:
    source_version_id: str
    source_url: str
    source_rule: dict
    inspect_data: dict = field(default_factory=dict)
    validate_patch: Callable[[dict], dict] | None = None
    request_review: Callable[[dict], dict] | None = None


class SourceBuildToolExecutor:
    """Bounded source-build operations; it never publishes or writes versions."""

    def __init__(self, context: SourceBuildToolContext):
        self._context = context
        self._pending_patch: dict | None = None
        self._validation: dict | None = None

    @property
    def pending_patch(self) -> dict | None:
        return deepcopy(self._pending_patch) if self._pending_patch is not None else None

    @property
    def validation(self) -> dict | None:
        return deepcopy(self._validation) if self._validation is not None else None

    def handlers(self) -> dict[str, Callable[[dict], ToolResult]]:
        return {
            'source.inspect': self._inspect,
            'source.probe': self._probe,
            'rule.propose': self._propose,
            'rule.validate': self._validate,
            'review.request': self._review,
        }

    def _inspect(self, _arguments: dict) -> ToolResult:
        return ToolResult(status='accepted', data={
            'source_version_id': self._context.source_version_id,
            'url': self._context.source_url,
            'source_rule': deepcopy(self._context.source_rule),
            **deepcopy(self._context.inspect_data),
        })

    def _probe(self, _arguments: dict) -> ToolResult:
        return ToolResult(status='accepted', data=deepcopy(self._context.inspect_data.get('probe_summary') or {}))

    def _propose(self, arguments: dict) -> ToolResult:
        patch = arguments.get('patch')
        if not isinstance(patch, dict) or not patch or set(patch) - ALLOWED_PATCH_FIELDS:
            return ToolResult(status='rejected', error_code='invalid_rule_patch')
        self._pending_patch = deepcopy(patch)
        return ToolResult(status='accepted', data={'patch_fields': sorted(patch)})

    def _validate(self, arguments: dict) -> ToolResult:
        patch = arguments.get('patch', self._pending_patch)
        if not isinstance(patch, dict) or not patch or set(patch) - ALLOWED_PATCH_FIELDS:
            return ToolResult(status='rejected', error_code='invalid_rule_patch')
        if self._context.validate_patch is None:
            return ToolResult(status='rejected', error_code='validation_unavailable')
        self._validation = self._context.validate_patch(deepcopy(patch))
        return ToolResult(status='accepted', data=deepcopy(self._validation))

    def _review(self, arguments: dict) -> ToolResult:
        if self._context.request_review is None:
            return ToolResult(status='rejected', error_code='review_unavailable')
        return ToolResult(status='accepted', data=self._context.request_review(deepcopy(arguments)))
