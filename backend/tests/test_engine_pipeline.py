from app.infrastructure.legado.engine.evaluator import evaluate_source_rules
from app.infrastructure.legado.engine.executor import execute_rule
from app.infrastructure.legado.engine.harness import run_rule_harness
from app.infrastructure.legado.engine.parser import parse_rule
from app.infrastructure.legado.engine.repairer import repair_source_rules
from app.infrastructure.legado.engine.validator import validate_source_rules


def test_parse_rule_detects_json_css_xpath_and_js():
    assert parse_rule("$.items[*].name").rule_type == "jsonpath"
    assert parse_rule("@css:.book-item").rule_type == "css"
    assert parse_rule("//div[@id='content']").rule_type == "xpath"
    assert parse_rule("@js:return result").rule_type == "js"


def test_validate_and_evaluate_return_structured_diagnostics():
    source = {"bookSourceName": "demo", "ruleSearch": {}, "ruleToc": {}, "ruleContent": {}}
    validation = validate_source_rules(source)
    assert validation.valid is False
    assert validation.errors

    evaluation = evaluate_source_rules(source)
    assert evaluation.score >= 0
    assert isinstance(evaluation.issues, list)


def test_repair_and_harness_return_structured_results():
    source = {"bookSourceName": "demo", "ruleSearch": "$.items[*].name", "ruleToc": "", "ruleContent": ""}
    repaired = repair_source_rules(source)
    assert repaired.changed is True
    assert repaired.updated["enabled"] is True

    parsed = parse_rule("$.items[*].name")
    execution = execute_rule(parsed, {"items": [{"name": "Book A"}]})
    assert execution.values == ["Book A"]

    harness = run_rule_harness("$.items[*].name", {"items": [{"name": "Book A"}]})
    assert harness.success is True
