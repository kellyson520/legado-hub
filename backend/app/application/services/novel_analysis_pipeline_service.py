from app.domain.entities.novel_analysis_task import AdjudicationOutcome


ROLE_GROUPS = {
    "extractor": "novel_extract",
    "verifier": "novel_verify",
    "adjudicator": "novel_adjudicate",
    "auditor": "novel_audit",
}


class NovelAnalysisPipelineService:
    def __init__(self, *, knowledge_service):
        self._knowledge_service = knowledge_service

    async def process_claim(self, claim_id: str, *, tenant_id: str) -> AdjudicationOutcome:
        claim = self._knowledge_service.get_claim(claim_id)
        if claim is None:
            raise LookupError("knowledge claim not found")
        if claim.epistemic == "speculative":
            return AdjudicationOutcome("human_review", "candidate", ("speculative claim",))
        if claim.predicate in {"same_identity_as", "identity_merge", "retcon"}:
            return AdjudicationOutcome("human_review", "candidate", ("identity or retcon escalation",))
        return AdjudicationOutcome("candidate", "candidate", ("awaiting independent verification",))
