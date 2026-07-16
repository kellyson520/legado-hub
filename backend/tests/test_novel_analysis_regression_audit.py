import pytest


@pytest.mark.asyncio
async def test_variant_change_reaudits_only_linked_claims():
    from app.application.services.novel_analysis_audit_service import NovelAnalysisAuditService

    class EvidenceRepo:
        def list_spans_for_variant(self, variant_id):
            assert variant_id == "variant-1"
            return [type("Span", (), {"id": "span-1"})()]

    class NarrativeRepo:
        def list_claim_ids_for_evidence(self, evidence_ids):
            assert evidence_ids == ["span-1"]
            return ["claim-linked"]

    result = await NovelAnalysisAuditService(EvidenceRepo(), NarrativeRepo()).reaudit_content_variant("variant-1")

    assert result.reaudited_claim_ids == ["claim-linked"]
