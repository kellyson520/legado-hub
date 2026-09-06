from __future__ import annotations

import inspect
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

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
    validate_patch: Callable[[dict], dict | Awaitable[dict]] | None = None
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

    def handlers(self) -> dict[str, Callable[[dict], ToolResult | Awaitable[ToolResult]]]:
        return {
            'source.inspect': self._inspect,
            'source.probe': self._probe,
            'rule.propose': self._propose,
            'rule.validate': self._validate,
            'rule.infer': self._infer,
            'review.request': self._review,
        }

    def _infer(self, arguments: dict) -> ToolResult:
        html = arguments.get('html') or self._context.inspect_data.get('html_sample') or ''
        if not html:
            return ToolResult(status='rejected', error_code='missing_html_sample')
        from app.application.services.source_induction_service import SourceInductionService
        induction = SourceInductionService()
        inferred = induction.infer_source_from_html(
            base_url=self._context.source_url,
            toc_html=html,
            content_html=arguments.get('content_html'),
            search_html=arguments.get('search_html'),
        )
        return ToolResult(status='accepted', data={'inferred_source': inferred})

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

    def _validate(self, arguments: dict) -> ToolResult | Awaitable[ToolResult]:
        patch = arguments.get('patch', self._pending_patch)
        if not isinstance(patch, dict) or not patch or set(patch) - ALLOWED_PATCH_FIELDS:
            return ToolResult(status='rejected', error_code='invalid_rule_patch')
        if self._context.validate_patch is None:
            return ToolResult(status='rejected', error_code='validation_unavailable')
        validation = self._context.validate_patch(deepcopy(patch))
        if inspect.isawaitable(validation):
            return self._await_validation(validation)
        return self._record_validation(validation)

    async def _await_validation(self, validation: Awaitable[dict]) -> ToolResult:
        try:
            return self._record_validation(await validation)
        except Exception:
            return ToolResult(status='rejected', error_code='validation_failed')

    def _record_validation(self, validation: Any) -> ToolResult:
        if not isinstance(validation, dict):
            return ToolResult(status='rejected', error_code='invalid_validation_result')
        self._validation = deepcopy(validation)
        return ToolResult(status='accepted', data=deepcopy(self._validation))

    def _review(self, arguments: dict) -> ToolResult:
        if self._context.request_review is None:
            return ToolResult(status='rejected', error_code='review_unavailable')
        if not self._full_validation_passed():
            return ToolResult(status='rejected', error_code='full_validation_required')
        return ToolResult(status='accepted', data=self._context.request_review(deepcopy(arguments)))

    def _full_validation_passed(self) -> bool:
        if not isinstance(self._validation, dict):
            return False
        return all(
            isinstance(self._validation.get(stage), dict)
            and self._validation[stage].get('passed') is True
            for stage in ('search', 'toc', 'content')
        )
