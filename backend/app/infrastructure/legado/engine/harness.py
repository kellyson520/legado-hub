from app.infrastructure.legado.engine.executor import execute_rule
from app.infrastructure.legado.engine.models import HarnessResult
from app.infrastructure.legado.engine.parser import parse_rule


def run_rule_harness(raw_rule: str, sample: str | dict) -> HarnessResult:
    parsed = parse_rule(raw_rule)
    execution = execute_rule(parsed, sample)
    return HarnessResult(
        success=not execution.diagnostics,
        parsed_rule=parsed,
        execution=execution,
        diagnostics=execution.diagnostics,
    )
