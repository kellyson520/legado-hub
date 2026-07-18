from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .native_models import RuntimeResult


def load_fixture_cases(directory: str | Path) -> list[dict[str, Any]]:
    root = Path(directory)
    cases: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"fixture must contain a list: {path}")
        for case in payload:
            if not isinstance(case, dict) or not case.get("name"):
                raise ValueError(f"fixture case must be an object with name: {path}")
            cases.append(case)
    return cases


def compare_runtime_results(expected: RuntimeResult, actual: RuntimeResult) -> dict[str, Any]:
    mismatches: list[str] = []
    if expected.success != actual.success:
        mismatches.append("success")
    if expected.value != actual.value:
        mismatches.append("value")
    if expected.value_type != actual.value_type:
        mismatches.append("value_type")
    if expected.error_code != actual.error_code:
        mismatches.append("error_code")
    return {
        "code": "NATIVE_SEMANTICS_MISMATCH" if mismatches else "OK",
        "mismatch_fields": mismatches,
    }
