from dataclasses import dataclass


@dataclass(frozen=True)
class ReauditResult:
    reaudited_claim_ids: list[str]


class NovelAnalysisAuditService:
    def __init__(self, evidence_repo, narrative_repo):
        self._evidence_repo = evidence_repo
        self._narrative_repo = narrative_repo

    async def reaudit_content_variant(self, variant_id: str) -> ReauditResult:
        evidence_ids = [span.id for span in self._evidence_repo.list_spans_for_variant(variant_id)]
        return ReauditResult(self._narrative_repo.list_claim_ids_for_evidence(evidence_ids))
