from dataclasses import dataclass, field

from app.application.services.site_profile_service import SiteProfile, SiteProfileService


@dataclass(frozen=True)
class SourceRepairDecision:
    strategy: str
    model_budget: int
    model_context: dict = field(default_factory=dict)
    outcome_tags: tuple[str, ...] = ()


class AgentPolicyService:
    _CONTEXT_KEYS = (
        'dom_signature',
        'request_summary',
        'response_summary',
        'sampled_content',
        'patch_candidate',
    )

    def __init__(self, profile_service: SiteProfileService | None = None):
        self._profiles = profile_service or SiteProfileService()

    def plan_source_repair(
        self,
        profile: SiteProfile,
        evidence: dict,
        *,
        budget_remaining: int = 600,
    ) -> SourceRepairDecision:
        matched = profile.matches(evidence)
        base_tags = list(self._profiles.build_outcome_tags(profile, matched=matched))

        if self._can_use_deterministic_patch(profile, matched=matched):
            patch_candidate = evidence.get('patch_candidate') or profile.template_patch or {}
            return SourceRepairDecision(
                strategy='deterministic_patch',
                model_budget=0,
                model_context={
                    'dom_signature': evidence.get('dom_signature'),
                    'patch_candidate': patch_candidate,
                },
                outcome_tags=tuple([*base_tags, 'strategy:deterministic_patch']),
            )

        if budget_remaining > 0 and profile.risk_level != 'high':
            bounded_budget = min(max(budget_remaining, 0), 600)
            return SourceRepairDecision(
                strategy='llm_repair',
                model_budget=bounded_budget,
                model_context=self._bounded_model_context(evidence),
                outcome_tags=tuple([*base_tags, 'strategy:llm_repair']),
            )

        blocked_reason = 'budget:blocked' if budget_remaining <= 0 else 'risk:blocked'
        return SourceRepairDecision(
            strategy='manual_review',
            model_budget=0,
            model_context=self._bounded_model_context(evidence),
            outcome_tags=tuple([*base_tags, 'strategy:manual_review', blocked_reason]),
        )

    @staticmethod
    def _can_use_deterministic_patch(profile: SiteProfile, *, matched: bool) -> bool:
        return (
            matched
            and bool(profile.template_patch)
            and profile.fixture_coverage >= 0.75
            and profile.confidence >= 0.7
            and profile.risk_level != 'high'
        )

    def _bounded_model_context(self, evidence: dict) -> dict:
        return {
            key: evidence[key]
            for key in self._CONTEXT_KEYS
            if key in evidence and evidence[key] not in (None, '')
        }
