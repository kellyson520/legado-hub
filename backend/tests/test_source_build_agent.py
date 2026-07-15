def test_source_build_agent_canaries_a_deterministic_patch():
    from app.application.services.agent_policy_service import AgentPolicyService
    from app.application.services.site_profile_service import SiteProfile
    from app.application.services.source_build_agent import SourceBuildAgent

    agent = SourceBuildAgent(policy=AgentPolicyService())
    profile = SiteProfile(
        site_id='example.test',
        dom_signatures={'sig-1'},
        template_patch={'selector': '#book-list'},
        fixture_coverage=0.95,
        confidence=0.92,
        risk_level='low',
    )

    result = agent.attempt_repair(
        candidate_url='https://example.test/books',
        profile=profile,
        evidence={'dom_signature': 'sig-1', 'patch_candidate': {'selector': '#book-list'}},
        fixture_validation_passed=True,
        sample_validation_passed=True,
    )

    assert result.decision == 'canary'
    assert result.review_required is False
    assert result.strategy == 'deterministic_patch'
    assert result.attempt_count == 1


def test_source_build_agent_uses_ai_when_template_fails_full_chain_validation():
    from app.application.services.agent_policy_service import AgentPolicyService
    from app.application.services.site_profile_service import SiteProfile
    from app.application.services.source_build_agent import SourceBuildAgent

    result = SourceBuildAgent(policy=AgentPolicyService()).attempt_repair(
        candidate_url='https://www.bqgiu.cc/',
        profile=SiteProfile(
            site_id='bqgiu', dom_signatures={'compat:bqgiu'}, template_patch={'ruleContent': '#content'},
            fixture_coverage=2 / 3, confidence=0.8, risk_level='medium',
        ),
        evidence={'dom_signature': 'compat:bqgiu', 'sampled_content': 'verification wall'},
        budget_remaining=600,
        fixture_validation_passed=True,
        sample_validation_passed=False,
    )

    assert result.strategy == 'llm_repair'
    assert result.decision == 'defer'


def test_source_build_agent_uses_ai_for_an_authorized_high_risk_probe_failure():
    from app.application.services.agent_policy_service import AgentPolicyService
    from app.application.services.site_profile_service import SiteProfile
    from app.application.services.source_build_agent import SourceBuildAgent

    result = SourceBuildAgent(policy=AgentPolicyService()).attempt_repair(
        candidate_url='https://unknown.test/',
        profile=SiteProfile(site_id='unknown.test', risk_level='high'),
        evidence={'dom_signature': 'unknown-signature'},
        budget_remaining=600,
        fixture_validation_passed=False,
        sample_validation_passed=False,
        allow_high_risk_llm=True,
    )

    assert result.strategy == 'llm_repair'
    assert result.decision == 'defer'


def test_source_build_agent_escalates_to_review_when_policy_blocks_automation():
    from app.application.services.agent_policy_service import AgentPolicyService
    from app.application.services.site_profile_service import SiteProfile
    from app.application.services.source_build_agent import SourceBuildAgent

    agent = SourceBuildAgent(policy=AgentPolicyService())
    profile = SiteProfile(
        site_id='example.test',
        dom_signatures=set(),
        fixture_coverage=0.1,
        confidence=0.2,
        risk_level='high',
    )

    result = agent.attempt_repair(
        candidate_url='https://example.test/books',
        profile=profile,
        evidence={'dom_signature': 'sig-9', 'sampled_content': '<html>blocked</html>'},
        budget_remaining=0,
        fixture_validation_passed=False,
        sample_validation_passed=False,
    )

    assert result.decision == 'escalate'
    assert result.review_required is True
    assert result.review_item is not None
    assert result.review_item['candidate_url'] == 'https://example.test/books'
    assert result.review_item['reason_tags'][-1] == 'budget:blocked'


def test_source_build_agent_persists_review_queue_item_when_escalated(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-agent-review.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.agent_policy_service import AgentPolicyService
    from app.application.services.site_profile_service import SiteProfile
    from app.application.services.source_build_agent import SourceBuildAgent
    from app.application.services.source_review_service import SourceReviewService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_review_repo_impl import SQLiteSourceReviewRepository

    bootstrap_sqlite()
    review_service = SourceReviewService(SQLiteSourceReviewRepository())
    agent = SourceBuildAgent(policy=AgentPolicyService(), review_service=review_service)
    profile = SiteProfile(
        site_id='example.test',
        dom_signatures=set(),
        fixture_coverage=0.1,
        confidence=0.2,
        risk_level='high',
    )

    result = agent.attempt_repair(
        candidate_url='https://example.test/books',
        profile=profile,
        evidence={'dom_signature': 'sig-9', 'sampled_content': '<html>blocked</html>'},
        budget_remaining=0,
        fixture_validation_passed=False,
        sample_validation_passed=False,
        source_version_id='source-version-1',
        actor_id='builder-1',
    )

    assert result.review_item is not None
    assert result.review_item['id']

    stored = SQLiteSourceReviewRepository().get_item(result.review_item['id'])
    assert stored is not None
    assert stored.review_type == 'build_escalation'
    assert stored.source_version_id == 'source-version-1'
    assert stored.created_by == 'builder-1'
    assert stored.payload['reason_tags'][-1] == 'budget:blocked'
