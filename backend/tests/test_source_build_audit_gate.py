from app.application.services.source_build_audit_service import SourceBuildAuditService


def test_deterministic_success_is_publishable_without_llm_review_agent():
    assert SourceBuildAuditService._review_gate_passed(
        audit={"workflow": "unified"},
        autonomous_build={"agent": {"status": "not_requested", "reason": "deterministic_success"}},
    ) is True
