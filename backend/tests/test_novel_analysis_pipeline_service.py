from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_identity_merge_escalates_even_when_models_agree():
    from app.application.services.novel_analysis_pipeline_service import NovelAnalysisPipelineService

    claim = SimpleNamespace(
        id="claim-1",
        predicate="same_identity_as",
        epistemic="explicit",
        evidence_ids=["span-1", "span-2"],
    )

    class Knowledge:
        def get_claim(self, claim_id):
            return claim if claim_id == "claim-1" else None

    pipeline = NovelAnalysisPipelineService(knowledge_service=Knowledge())
    outcome = await pipeline.process_claim("claim-1", tenant_id="tenant-1")

    assert outcome.verdict == "human_review"
    assert outcome.claim_status == "candidate"
