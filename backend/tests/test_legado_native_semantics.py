from app.infrastructure.legado.engine.js_session_models import JsCompatDiff, JsExecutionTrace
from app.infrastructure.legado.engine.legado_native_semantics import LegadoJsCompatProfile


def test_native_profile_builds_stage_context_with_expected_variables():
    profile = LegadoJsCompatProfile.native_defaults()

    context = profile.build_context(
        stage="search_url_js",
        source={"bookSourceName": "测试源", "bookSourceUrl": "https://novel.cooks.tw"},
        book={"name": "斗罗大陆"},
        result=None,
        base_url="https://novel.cooks.tw",
        cache={"articleid": 362918},
        variables={"keyword": "斗罗大陆", "page": 1, "searchKey": "斗罗大陆"},
        headers={"User-Agent": "pytest-agent"},
    )

    assert context.stage == "search_url_js"
    assert context.source["bookSourceUrl"] == "https://novel.cooks.tw"
    assert context.variables["keyword"] == "斗罗大陆"
    assert context.cache["articleid"] == 362918
    assert context.headers["User-Agent"] == "pytest-agent"


def test_compat_diff_marks_native_mismatch_with_cache_keys():
    diff = JsCompatDiff.compare(
        expected_value={"url": "/search?wd=斗罗大陆"},
        actual_value={"url": "/search?wd=斗破苍穹"},
        expected_cache={"articleid": 362918},
        actual_cache={"articleid": 9527},
        trace=JsExecutionTrace(stage="search_url_js", success=False, rule_preview="return result"),
    )

    assert diff.code == "NATIVE_SEMANTICS_MISMATCH"
    assert "value" in diff.mismatch_fields
    assert "cache.articleid" in diff.mismatch_fields
