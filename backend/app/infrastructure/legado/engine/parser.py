from app.infrastructure.legado.engine.models import ParsedRule


def _extract_operations(expression: str) -> tuple[str, list[dict]]:
    selector = expression
    operations: list[dict] = []

    if "@replace:" in selector:
        selector, replace_part = selector.split("@replace:", 1)
        if "=>" in replace_part:
            old, new = replace_part.split("=>", 1)
            operations.append({"kind": "replace", "old": old, "new": new})

    marker_count = selector.count("##")
    if marker_count >= 2:
        base, pattern, replacement = selector.split("##", 2)
        selector = base
        operations.insert(0, {"kind": "regex_replace", "pattern": pattern, "replacement": replacement})

    return selector.strip(), operations


def parse_rule(raw: str) -> ParsedRule:
    rule = (raw or "").strip()
    if rule.startswith("@css:"):
        expression, operations = _extract_operations(rule[5:])
        return ParsedRule(raw=raw, rule_type="css", expression=expression, operations=operations)
    if rule.startswith("@js:"):
        return ParsedRule(raw=raw, rule_type="js", expression=rule[4:])
    if rule.startswith("//") or rule.startswith("./"):
        expression, operations = _extract_operations(rule)
        return ParsedRule(raw=raw, rule_type="xpath", expression=expression, operations=operations)
    if rule.startswith("$"):
        expression, operations = _extract_operations(rule)
        return ParsedRule(raw=raw, rule_type="jsonpath", expression=expression, operations=operations)
    return ParsedRule(raw=raw, rule_type="auto", expression=rule)
