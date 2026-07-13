from bs4 import BeautifulSoup
from lxml import etree

from app.infrastructure.legado.engine.jsonpath_ext import run_jsonpath
from app.infrastructure.legado.engine.js_runtime import JsRuntime
from app.infrastructure.legado.engine.models import ExecutionResult, ParsedRule
from app.infrastructure.legado.engine.text_pipeline import apply_rule_operations


def execute_rule(rule: ParsedRule, sample: str | dict) -> ExecutionResult:
    try:
        if rule.rule_type == "jsonpath":
            values = run_jsonpath(rule.expression, sample)
            return ExecutionResult(values=apply_rule_operations(values, rule.operations), diagnostics=[])
        if rule.rule_type == "css" and isinstance(sample, str):
            soup = BeautifulSoup(sample, "lxml")
            values = [item.get_text(strip=True) for item in soup.select(rule.expression)]
            return ExecutionResult(values=apply_rule_operations(values, rule.operations), diagnostics=[])
        if rule.rule_type == "xpath" and isinstance(sample, str):
            tree = etree.HTML(sample)
            result = tree.xpath(rule.expression)
            values = [item if isinstance(item, str) else getattr(item, "text", "") for item in result]
            values = [value for value in values if value]
            return ExecutionResult(values=apply_rule_operations(values, rule.operations), diagnostics=[])
        if rule.rule_type == "js":
            runtime = JsRuntime()
            value = runtime.execute(rule.expression, sample)
            if value is None:
                return ExecutionResult(values=[], diagnostics=["js runtime returned no value"])
            if isinstance(value, list):
                return ExecutionResult(values=[str(item) for item in value], diagnostics=[])
            return ExecutionResult(values=[str(value)], diagnostics=[])
        return ExecutionResult(values=[], diagnostics=[f"unsupported rule type: {rule.rule_type}"])
    except Exception as exc:
        return ExecutionResult(values=[], diagnostics=[str(exc)])
