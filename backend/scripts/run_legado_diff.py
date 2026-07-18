from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.legado.engine.native_models import RuntimeResult
from app.infrastructure.legado.engine.runtime_diff import compare_runtime_results, load_fixture_cases
from app.infrastructure.legado.engine.runtime_facade import LegadoRuntimeFacade, PythonRuntimeFallback


def run_case(case: dict, *, python_only: bool) -> dict:
    expected = RuntimeResult(
        success=True,
        value=case.get("expected_value"),
        value_type=case.get("expected_type"),
    )
    if python_only:
        actual = PythonRuntimeFallback().extract(
            case.get("content"),
            case["rule"],
            operation=case.get("operation", "extract_string"),
            base_url=case.get("base_url", ""),
            is_html=isinstance(case.get("content"), str),
            context={},
        )
    else:
        facade = LegadoRuntimeFacade(mode="native_kotlin")
        try:
            if case.get("operation") == "resolve_url":
                actual = facade.resolve_url(case["rule"], base_url=case.get("base_url", ""))
            else:
                actual = facade.extract(
                    case.get("content"),
                    case["rule"],
                    operation=case.get("operation", "extract_string"),
                    base_url=case.get("base_url", ""),
                    stage="diff",
                )
        finally:
            facade.close()
    diff = compare_runtime_results(expected, actual)
    return {
        "name": case["name"],
        "expected": expected.__dict__,
        "actual": actual.__dict__,
        "diff": diff,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--python-only", action="store_true")
    parser.add_argument("--format", choices=("json", "pretty"), default="pretty")
    args = parser.parse_args(argv)

    results = [run_case(case, python_only=args.python_only) for case in load_fixture_cases(args.fixtures)]
    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    else:
        for result in results:
            print(f"{result['name']}: {result['diff']['code']}")
            if result["diff"]["mismatch_fields"]:
                print(json.dumps(result, ensure_ascii=False, default=str))
    return 1 if any(result["diff"]["code"] != "OK" for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
