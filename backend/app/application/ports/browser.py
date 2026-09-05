from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserAttemptResult:
    state: str
    reason: str = ''

    @classmethod
    def needs_manual(cls, reason: str) -> 'BrowserAttemptResult':
        return cls(state='needs_manual', reason=reason)

    @classmethod
    def succeeded(cls) -> 'BrowserAttemptResult':
        return cls(state='succeeded')


@dataclass(frozen=True)
class BrowserValidationResult:
    passed: bool
    reason: str = ''
    stages: dict[str, dict] | None = None

    @classmethod
    def passed(cls, stages: dict[str, dict]) -> 'BrowserValidationResult':
        return cls(passed=True, stages=stages)

    @classmethod
    def failed(cls, reason: str, stages: dict[str, dict]) -> 'BrowserValidationResult':
        return cls(passed=False, reason=reason, stages=stages)
