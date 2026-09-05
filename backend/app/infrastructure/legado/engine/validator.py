from app.infrastructure.legado.engine.models import ValidationResult
from app.infrastructure.legado.engine.parser import parse_rule


def validate_source_rules(source: dict) -> ValidationResult:
    missing = []
    for field in ("ruleSearch", "ruleToc", "ruleContent"):
        if not source.get(field):
            missing.append(f"missing {field}")
    warnings = []
    for field in ("ruleSearch", "ruleToc", "ruleContent"):
        value = source.get(field)
        if isinstance(value, str) and value:
            parsed = parse_rule(value)
            if parsed.rule_type == "auto":
                warnings.append(f"{field} uses auto-detected syntax")
    return ValidationResult(valid=not missing, errors=missing, warnings=warnings)
