from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JsExecutionContext:
    stage: str
    source: dict[str, Any] = field(default_factory=dict)
    book: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    base_url: str = ""
    cache: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class JsExecutionTrace:
    stage: str
    success: bool
    rule_preview: str
    builtin_hit: bool = False
    worker_elapsed_ms: int = 0
    bridge_http_count: int = 0
    cache_keys_written: list[str] = field(default_factory=list)
    error_code: str | None = None


@dataclass
class JsCompatDiff:
    code: str
    mismatch_fields: list[str] = field(default_factory=list)
    expected_value: Any = None
    actual_value: Any = None
    expected_cache: dict[str, Any] = field(default_factory=dict)
    actual_cache: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def compare(
        cls,
        expected_value: Any,
        actual_value: Any,
        expected_cache: dict[str, Any],
        actual_cache: dict[str, Any],
        trace: JsExecutionTrace,
    ) -> "JsCompatDiff":
        mismatches: list[str] = []
        if expected_value != actual_value:
            mismatches.append("value")
        for key in sorted(set(expected_cache) | set(actual_cache)):
            if expected_cache.get(key) != actual_cache.get(key):
                mismatches.append(f"cache.{key}")
        code = "NATIVE_SEMANTICS_MISMATCH" if mismatches else "OK"
        return cls(
            code=code,
            mismatch_fields=mismatches,
            expected_value=expected_value,
            actual_value=actual_value,
            expected_cache=expected_cache,
            actual_cache=actual_cache,
        )
