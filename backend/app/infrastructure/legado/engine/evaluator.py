from app.infrastructure.legado.engine.models import EvaluationResult
from app.infrastructure.legado.engine.validator import validate_source_rules


def evaluate_source_rules(source: dict) -> EvaluationResult:
    validation = validate_source_rules(source)
    score = 100 - len(validation.errors) * 30 - len(validation.warnings) * 10
    score = max(score, 0)
    grade = "A" if score >= 90 else "B" if score >= 70 else "C" if score >= 50 else "D"
    return EvaluationResult(
        score=score,
        grade=grade,
        issues=validation.errors + validation.warnings,
        usable=validation.valid and score >= 70,
    )
