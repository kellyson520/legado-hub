from dataclasses import dataclass, field
from uuid import uuid4

from app.application.services.agent_policy_service import AgentPolicyService
from app.application.services.source_review_service import SourceReviewService
from app.application.services.site_profile_service import SiteProfile


@dataclass(frozen=True)
class SourceBuildStep:
    name: str
    passed: bool
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SourceBuildAgentResult:
    decision: str
    strategy: str
    review_required: bool
    attempt_count: int
    review_item: dict | None = None
    attempt_id: str = ""
    status: str = ""
    steps: tuple[SourceBuildStep, ...] = ()
    reason_tags: tuple[str, ...] = ()


class SourceBuildAgent:
    def __init__(
        self,
        *,
        policy: AgentPolicyService | None = None,
        review_service: SourceReviewService | None = None,
    ):
        self._policy = policy or AgentPolicyService()
        self._review_service = review_service

    def attempt_repair(
        self,
        *,
        candidate_url: str,
        profile: SiteProfile,
        evidence: dict,
        budget_remaining: int = 600,
        fixture_validation_passed: bool,
        sample_validation_passed: bool,
        allow_high_risk_llm: bool = False,
        source_version_id: str | None = None,
        actor_id: str = 'system',
    ) -> SourceBuildAgentResult:
        result = self.run_workflow(
            candidate_url=candidate_url,
            profile=profile,
            evidence=evidence,
            budget_remaining=budget_remaining,
            fixture_validation_passed=fixture_validation_passed,
            sample_validation_passed=sample_validation_passed,
            allow_high_risk_llm=allow_high_risk_llm,
            source_version_id=source_version_id,
            actor_id=actor_id,
        )
        return SourceBuildAgentResult(
            decision=result.decision,
            strategy=result.strategy,
            review_required=result.review_required,
            attempt_count=result.attempt_count,
            review_item=result.review_item,
            attempt_id=result.attempt_id,
            status=result.status,
            steps=result.steps,
            reason_tags=result.reason_tags,
        )

    def run_workflow(
        self,
        *,
        candidate_url: str,
        profile: SiteProfile,
        evidence: dict,
        budget_remaining: int = 600,
        fixture_validation_passed: bool,
        sample_validation_passed: bool,
        allow_high_risk_llm: bool = False,
        source_version_id: str | None = None,
        actor_id: str = 'system',
    ) -> SourceBuildAgentResult:
        attempt_id = uuid4().hex
        decision = self._policy.plan_source_repair(
            profile,
            evidence,
            budget_remaining=budget_remaining,
            allow_high_risk_llm=allow_high_risk_llm,
        )
        steps = [SourceBuildStep("planned", True, {"strategy": decision.strategy})]
        steps.append(SourceBuildStep("proposed", True, {"reason_tags": list(decision.outcome_tags)}))

        if decision.strategy == 'deterministic_patch':
            steps.append(SourceBuildStep(
                "validating",
                bool(fixture_validation_passed and sample_validation_passed),
                {
                    "fixture": bool(fixture_validation_passed),
                    "sample": bool(sample_validation_passed),
                },
            ))
            if fixture_validation_passed and sample_validation_passed:
                steps.append(SourceBuildStep("canary", True))
                return SourceBuildAgentResult(
                    decision='canary', strategy=decision.strategy, review_required=False,
                    attempt_count=1, attempt_id=attempt_id, status='canary',
                    steps=tuple(steps), reason_tags=decision.outcome_tags,
                )

        if decision.strategy == 'llm_repair' and budget_remaining > 0:
            steps.append(SourceBuildStep("deferred", True, {"model_budget": decision.model_budget}))
            return SourceBuildAgentResult(
                decision='defer', strategy=decision.strategy, review_required=False,
                attempt_count=1, attempt_id=attempt_id, status='deferred',
                steps=tuple(steps), reason_tags=decision.outcome_tags,
            )

        review_item = {
            'candidate_url': candidate_url,
            'reason_tags': list(decision.outcome_tags),
            'model_context': decision.model_context,
        }
        if self._review_service is not None:
            persisted = self._review_service.enqueue_build_escalation(
                source_version_id=source_version_id,
                source_url=candidate_url,
                reason_tags=list(decision.outcome_tags),
                model_context=decision.model_context,
                created_by=actor_id,
            )
            review_item = review_item | {
                'id': persisted.id,
                'status': persisted.status,
                'created_by': persisted.created_by,
                'created_at': persisted.created_at.isoformat() if persisted.created_at else None,
            }
        steps.append(SourceBuildStep("escalated", False, {"review_required": True}))
        return SourceBuildAgentResult(
            decision='escalate', strategy=decision.strategy, review_required=True,
            attempt_count=1, review_item=review_item, attempt_id=attempt_id,
            status='escalated', steps=tuple(steps), reason_tags=decision.outcome_tags,
        )
