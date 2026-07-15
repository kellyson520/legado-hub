from app.application.services.agent_policy_service import AgentPolicyService
from app.application.services.site_profile_service import SiteProfile


def test_policy_uses_template_match_without_model_call():
    policy = AgentPolicyService()
    matching_profile = SiteProfile(
        site_id='example.test',
        dom_signatures={'sig-1'},
        template_patch={'selector': '#book-list'},
        fixture_coverage=0.95,
        confidence=0.92,
        risk_level='low',
    )

    decision = policy.plan_source_repair(
        matching_profile,
        evidence={
            'dom_signature': 'sig-1',
            'request_summary': {'url': 'https://example.test/search?q=sample'},
            'response_summary': {'status': 200},
            'sampled_content': '<div id="book-list"></div>',
            'patch_candidate': {'selector': '#book-list'},
            'full_html': '<html>very large document</html>',
        },
    )

    assert decision.strategy == 'deterministic_patch'
    assert decision.model_budget == 0
    assert decision.model_context == {
        'dom_signature': 'sig-1',
        'patch_candidate': {'selector': '#book-list'},
    }


def test_policy_falls_back_to_llm_with_bounded_context():
    policy = AgentPolicyService()
    profile = SiteProfile(
        site_id='example.test',
        dom_signatures={'sig-known'},
        fixture_coverage=0.2,
        confidence=0.38,
        risk_level='medium',
    )

    decision = policy.plan_source_repair(
        profile,
        evidence={
            'dom_signature': 'sig-unknown',
            'request_summary': {'url': 'https://example.test/search?q=sample'},
            'response_summary': {'status': 503, 'kind': 'html'},
            'sampled_content': '<html>challenge page</html>',
            'patch_candidate': {'selector': '.result-card'},
            'full_html': '<html>' + ('x' * 5000) + '</html>',
        },
        budget_remaining=900,
    )

    assert decision.strategy == 'llm_repair'
    assert decision.model_budget > 0
    assert set(decision.model_context.keys()) == {
        'dom_signature',
        'request_summary',
        'response_summary',
        'sampled_content',
        'patch_candidate',
    }
    assert 'full_html' not in decision.model_context


def test_policy_requires_manual_review_when_budget_is_exhausted_for_high_risk_change():
    policy = AgentPolicyService()
    profile = SiteProfile(
        site_id='example.test',
        dom_signatures=set(),
        fixture_coverage=0.1,
        confidence=0.22,
        risk_level='high',
    )

    decision = policy.plan_source_repair(
        profile,
        evidence={'dom_signature': 'sig-9', 'sampled_content': '<html>broken</html>'},
        budget_remaining=0,
    )

    assert decision.strategy == 'manual_review'
    assert decision.model_budget == 0
    assert decision.outcome_tags[-1] == 'budget:blocked'


def test_policy_allows_high_risk_repair_only_with_explicit_operator_authorization():
    decision = AgentPolicyService().plan_source_repair(
        SiteProfile(site_id='unknown.test', risk_level='high'),
        evidence={'dom_signature': 'unknown-signature'},
        budget_remaining=600,
        allow_high_risk_llm=True,
    )

    assert decision.strategy == 'llm_repair'
    assert decision.model_budget == 600
