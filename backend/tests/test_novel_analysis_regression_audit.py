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


@pytest.mark.asyncio
async def test_variant_reaudit_queues_only_tasks_for_claims_linked_to_that_variant():
    from app.application.services.novel_analysis_audit_service import NovelAnalysisAuditService

    class EvidenceRepo:
        def list_spans_for_variant(self, variant_id):
            assert variant_id == "variant-1"
            return [type("Span", (), {"id": "span-1"})()]

    class NarrativeRepo:
        def list_claim_ids_for_evidence(self, evidence_ids):
            assert evidence_ids == ["span-1"]
            return ["claim-linked"]

        def get_claim(self, claim_id):
            assert claim_id == "claim-linked"
            return type("Claim", (), {"id": claim_id, "work_id": "work-1", "evidence_ids": ["span-1"]})()

    class Tasks:
        def __init__(self):
            self.items = []

        def queue_reaudit(self, *, claim, tenant_id, policy):
            self.items.append((claim.id, tenant_id, policy))
            return type("Task", (), {"id": "task-1"})()

    tasks = Tasks()
    result = await NovelAnalysisAuditService(EvidenceRepo(), NarrativeRepo(), task_service=tasks).queue_reaudit_content_variant(
        "variant-1", tenant_id="tenant-1", policy={"max_tokens_per_task": 3000},
    )

    assert result.reaudited_claim_ids == ["claim-linked"]
    assert result.task_ids == ["task-1"]
    assert tasks.items == [("claim-linked", "tenant-1", {"max_tokens_per_task": 3000})]
