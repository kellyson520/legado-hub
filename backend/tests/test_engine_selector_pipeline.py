from app.infrastructure.legado.engine.harness import run_rule_harness


def test_harness_executes_regex_and_replace_chain():
    result = run_rule_harness("@css:.title##(.*)##$1@replace:Foo=>Bar", "<div class='title'>Foo Story</div>")
    assert result.execution.values == ["Bar Story"]


def test_harness_executes_js_with_timeout_guard():
    result = run_rule_harness("@js:return ['ok']", {"items": []})
    assert result.success is True
    assert result.execution.values == ["ok"]
