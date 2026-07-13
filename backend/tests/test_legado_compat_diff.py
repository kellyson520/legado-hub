from app.infrastructure.legado.engine.js_session_models import JsCompatDiff, JsExecutionTrace


def test_compat_diff_reports_ok_when_values_and_cache_match():
    diff = JsCompatDiff.compare(
        expected_value={"title": "斗罗大陆"},
        actual_value={"title": "斗罗大陆"},
        expected_cache={"articleid": 362918},
        actual_cache={"articleid": 362918},
        trace=JsExecutionTrace(stage="content_rule_js", success=True, rule_preview="doc.select('.title').text()"),
    )

    assert diff.code == "OK"
    assert diff.mismatch_fields == []
