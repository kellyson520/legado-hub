from dataclasses import dataclass, field


@dataclass
class ParsedRule:
    raw: str
    rule_type: str
    expression: str
    alternatives: list[str] = field(default_factory=list)
    operations: list[dict] = field(default_factory=list)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    values: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class EvaluationResult:
    score: int
    grade: str
    issues: list[str] = field(default_factory=list)
    usable: bool = False


@dataclass
class RepairResult:
    changed: bool
    updated: dict
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class HarnessResult:
    success: bool
    parsed_rule: ParsedRule
    execution: ExecutionResult
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class RuntimeExecutionSummary:
    step_results: dict[str, dict] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
