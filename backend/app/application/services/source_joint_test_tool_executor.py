from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from app.domain.entities.agent_runtime import ToolResult
from app.core.url_safety import SourceUrlPolicy
from app.core.redaction import sanitize_for_boundary


class _JointTestValidationError(ValueError):
    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


class SourceJointTestToolExecutor:
    """Candidate-only, bounded adapter for the source-to-insight workflow."""

    MAX_URLS = 4
    MAX_URL_LENGTH = 2048
    MAX_BOOK_NAME_LENGTH = 300
    MAX_AUTHOR_LENGTH = 200
    MAX_TITLE_LENGTH = 300
    MAX_CHAPTER_INDEX = 100_000
    MAX_PREVIEW_LENGTH = 1200
    MAX_RESULT_ITEMS = 12

    _ALLOWED_ARGUMENTS = frozenset({
        "tenant_id",
        "source_urls",
        "book_name",
        "author_hint",
        "chapter_index",
        "chapter_title",
        "use_ai",
    })

    def __init__(self, acceptance_service):
        self._acceptance_service = acceptance_service

    def handlers(self) -> dict[str, Any]:
        return {"source.joint_test": self.ainvoke}

    async def ainvoke(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            scenario = self._scenario(arguments)
        except _JointTestValidationError as exc:
            return ToolResult(status="rejected", error_code=exc.error_code)

        try:
            raw_report = await self._acceptance_service.run(scenario)
        except Exception:
            return ToolResult(status="rejected", error_code="acceptance_failed")
        if not isinstance(raw_report, dict):
            return ToolResult(status="rejected", error_code="invalid_acceptance_report")

        report = self._bound_report(raw_report)
        metadata = self._agent_metadata(report)
        return ToolResult(
            status="accepted",
            data={
                "report": report,
                "summary": self._summary(report),
                "agent_joint_test": metadata,
            },
        )

    @classmethod
    def _scenario(cls, arguments: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise _JointTestValidationError("invalid_arguments")
        unknown = set(arguments) - cls._ALLOWED_ARGUMENTS
        if unknown:
            raise _JointTestValidationError("unsupported_argument")

        tenant_id = cls._required_text(arguments.get("tenant_id"), "tenant_id_required", 200)
        raw_urls = arguments.get("source_urls")
        if not isinstance(raw_urls, list) or not raw_urls:
            raise _JointTestValidationError("source_urls_required")
        if len(raw_urls) > cls.MAX_URLS:
            raise _JointTestValidationError("source_urls_limit")
        source_urls = []
        for raw_url in raw_urls:
            url = cls._required_text(raw_url, "source_url_invalid", cls.MAX_URL_LENGTH)
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise _JointTestValidationError("source_url_invalid")
            if SourceUrlPolicy.public_http_url_error(url) == "unsafe":
                raise _JointTestValidationError("source_url_unsafe")
            source_urls.append(url)

        book_name = cls._required_text(
            arguments.get("book_name"), "book_name_required", cls.MAX_BOOK_NAME_LENGTH,
        )
        author_hint = cls._optional_text(arguments.get("author_hint"), "author_hint_invalid", cls.MAX_AUTHOR_LENGTH)
        chapter_title = cls._optional_text(
            arguments.get("chapter_title"), "chapter_title_invalid", cls.MAX_TITLE_LENGTH,
        )
        chapter_index = arguments.get("chapter_index", 0)
        if isinstance(chapter_index, bool) or not isinstance(chapter_index, int):
            raise _JointTestValidationError("chapter_index_invalid")
        if not 0 <= chapter_index <= cls.MAX_CHAPTER_INDEX:
            raise _JointTestValidationError("chapter_index_invalid")
        use_ai = arguments.get("use_ai", False)
        if not isinstance(use_ai, bool):
            raise _JointTestValidationError("use_ai_invalid")

        return {
            "tenant_id": tenant_id,
            "source_urls": source_urls,
            "book_name": book_name,
            "author_hint": author_hint,
            "chapter_index": chapter_index,
            "chapter_title": chapter_title,
            "use_ai": use_ai,
            "agent_joint_test": True,
        }

    @staticmethod
    def _required_text(value: Any, error_code: str, max_length: int) -> str:
        if not isinstance(value, str):
            raise _JointTestValidationError(error_code)
        normalized = value.strip()
        if not normalized or len(normalized) > max_length:
            raise _JointTestValidationError(error_code)
        return normalized

    @classmethod
    def _optional_text(cls, value: Any, error_code: str, max_length: int) -> str:
        if value is None:
            return ""
        return cls._required_text(value, error_code, max_length)

    @classmethod
    def _bound_report(cls, report: dict[str, Any]) -> dict[str, Any]:
        bounded = deepcopy(report)
        for key in ("source_builds", "book_candidates", "toc_candidates", "chapter_candidates", "steps"):
            value = bounded.get(key)
            if isinstance(value, list):
                bounded[key] = [cls._bound_value(item) for item in value[: cls.MAX_RESULT_ITEMS]]
        return cls._bound_value(bounded)

    @classmethod
    def _bound_value(cls, value: Any) -> Any:
        value = sanitize_for_boundary(value)
        if isinstance(value, str):
            return value if len(value) <= cls.MAX_PREVIEW_LENGTH else value[: cls.MAX_PREVIEW_LENGTH] + "..."
        if isinstance(value, list):
            return [cls._bound_value(item) for item in value[: cls.MAX_RESULT_ITEMS]]
        if isinstance(value, dict):
            raw_content = value.get("content")
            bounded = {key: cls._bound_value(item) for key, item in value.items()}
            if isinstance(raw_content, str):
                bounded["content_length"] = len(raw_content)
                bounded["content_preview"] = raw_content[: cls.MAX_PREVIEW_LENGTH]
                bounded.pop("content", None)
            return bounded
        return value

    @staticmethod
    def _agent_metadata(report: dict[str, Any]) -> dict[str, Any]:
        existing = report.get("agent_joint_test")
        metadata = dict(existing) if isinstance(existing, dict) else {}
        metadata.update({
            "enabled": True,
            "tool_name": "source.joint_test",
            "status": report.get("status", "unknown"),
            "steps": [
                step.get("name")
                for step in report.get("steps", [])
                if isinstance(step, dict) and step.get("name")
            ],
        })
        return metadata

    @staticmethod
    def _summary(report: dict[str, Any]) -> dict[str, Any]:
        steps = [step for step in report.get("steps", []) if isinstance(step, dict)]
        content_steps = [step for step in steps if step.get("name") == "content"]
        return {
            "status": report.get("status", "unknown"),
            "step_count": len(steps),
            "passed_steps": sum(step.get("status") == "passed" for step in steps),
            "failed_steps": sum(step.get("status") == "failed" for step in steps),
            "content_passed": sum(step.get("status") == "passed" for step in content_steps),
            "source_count": len(report.get("source_builds") or []),
            "chapter_candidate_count": len(report.get("chapter_candidates") or []),
        }
