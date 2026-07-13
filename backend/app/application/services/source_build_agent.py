from dataclasses import dataclass

from app.application.services.agent_policy_service import AgentPolicyService
from app.application.services.source_review_service import SourceReviewService
from app.application.services.site_profile_service import SiteProfile


@dataclass(frozen=True)
class SourceBuildAgentResult:
    decision: str
    strategy: str
    review_required: bool
    attempt_count: int
    review_item: dict | None = None


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
        source_version_id: str | None = None,
        actor_id: str = 'system',
    ) -> SourceBuildAgentResult:
        decision = self._policy.plan_source_repair(
            profile,
            evidence,
            budget_remaining=budget_remaining,
        )

        if (
            decision.strategy == 'deterministic_patch'
            and fixture_validation_passed
            and sample_validation_passed
        ):
            return SourceBuildAgentResult(
                decision='canary',
                strategy=decision.strategy,
                review_required=False,
                attempt_count=1,
            )

        if decision.strategy == 'llm_repair' and budget_remaining > 0:
            return SourceBuildAgentResult(
                decision='defer',
                strategy=decision.strategy,
                review_required=False,
                attempt_count=1,
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

        return SourceBuildAgentResult(
            decision='escalate',
            strategy=decision.strategy,
            review_required=True,
            attempt_count=1,
            review_item=review_item,
        )
