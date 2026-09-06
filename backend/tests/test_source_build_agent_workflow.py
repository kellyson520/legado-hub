from app.application.services.agent_policy_service import AgentPolicyService
from app.application.services.site_profile_service import SiteProfile
from app.application.services.source_build_agent import SourceBuildAgent


def _deterministic_profile():
    return SiteProfile(
        site_id="example.test",
        dom_signatures={"sig-1"},
        template_patch={"selector": "#book-list"},
        fixture_coverage=0.95,
        confidence=0.92,
        risk_level="low",
    )


def test_workflow_records_ordered_canary_steps():
    result = SourceBuildAgent(policy=AgentPolicyService()).run_workflow(
        candidate_url="https://example.test/books",
        profile=_deterministic_profile(),
        evidence={"dom_signature": "sig-1", "patch_candidate": {"selector": "#book-list"}},
        fixture_validation_passed=True,
        sample_validation_passed=True,
    )

    assert result.status == "canary"
    assert result.attempt_id
    assert [step.name for step in result.steps] == ["planned", "proposed", "validating", "canary"]
    assert all(step.passed for step in result.steps)


def test_workflow_escalates_failed_validation_instead_of_canary():
    result = SourceBuildAgent(policy=AgentPolicyService()).run_workflow(
        candidate_url="https://example.test/books",
        profile=_deterministic_profile(),
        evidence={"dom_signature": "sig-1"},
        fixture_validation_passed=True,
        sample_validation_passed=False,
    )

    assert result.status == "escalated"
    assert result.review_required is True
    assert result.review_item["candidate_url"] == "https://example.test/books"
    assert result.steps[-1].name == "escalated"
    assert result.steps[-1].passed is False


def test_workflow_defers_llm_repair_with_positive_budget():
    result = SourceBuildAgent(policy=AgentPolicyService()).run_workflow(
        candidate_url="https://unknown.test/",
        profile=SiteProfile(site_id="unknown.test", risk_level="high"),
        evidence={"dom_signature": "unknown"},
        budget_remaining=600,
        fixture_validation_passed=False,
        sample_validation_passed=False,
        allow_high_risk_llm=True,
    )

    assert result.status == "deferred"
    assert result.review_required is False
    assert result.steps[-1].name == "deferred"
