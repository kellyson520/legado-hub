from dataclasses import dataclass


@dataclass
class RuntimeHealthDecision:
    action: str
    new_status: str
    reason: str
    allowed: bool

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "new_status": self.new_status,
            "reason": self.reason,
            "allowed": self.allowed,
        }


def evaluate_runtime_health(version, run) -> RuntimeHealthDecision:
    if run is None:
        return RuntimeHealthDecision(
            action="quarantine",
            new_status="quarantined",
            reason="no health run available",
            allowed=False,
        )

    has_failures = any(not bool(detail.get("passed")) for detail in run.step_results.values())
    if run.score < 60 or has_failures:
        return RuntimeHealthDecision(
            action="rollback",
            new_status="rolled_back",
            reason="runtime health degraded",
            allowed=False,
        )

    return RuntimeHealthDecision(
        action="keep",
        new_status=version.status,
        reason="runtime health stable",
        allowed=True,
    )
