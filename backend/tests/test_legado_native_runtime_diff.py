import json
from pathlib import Path

from app.infrastructure.legado.engine.native_models import RuntimeResult
from app.infrastructure.legado.engine.runtime_diff import compare_runtime_results, load_fixture_cases


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "legado_runtime"


def test_golden_fixtures_cover_html_json_js_and_url_rules():
    cases = load_fixture_cases(FIXTURE_DIR)
    names = {case["name"] for case in cases}
    assert {"html-list-text", "json-list", "js-return-result", "relative-url"} <= names


def test_diff_compares_value_type_and_error_code():
    expected = RuntimeResult(success=True, value=["A"], value_type="list")
    actual = RuntimeResult(success=True, value=["B"], value_type="string")
    diff = compare_runtime_results(expected, actual)
    assert diff["code"] == "NATIVE_SEMANTICS_MISMATCH"
    assert diff["mismatch_fields"] == ["value", "value_type"]


def test_identical_runtime_results_have_no_diff():
    result = RuntimeResult(success=True, value="A", value_type="string")
    diff = compare_runtime_results(result, result)
    assert diff == {"code": "OK", "mismatch_fields": []}
