from dataclasses import dataclass


@dataclass(frozen=True)
class ReauditResult:
    reaudited_claim_ids: list[str]
    task_ids: list[str] | None = None


class NovelAnalysisAuditService:
    def __init__(self, evidence_repo, narrative_repo, task_service=None):
        self._evidence_repo = evidence_repo
        self._narrative_repo = narrative_repo
        self._task_service = task_service

    async def reaudit_content_variant(self, variant_id: str) -> ReauditResult:
        evidence_ids = [span.id for span in self._evidence_repo.list_spans_for_variant(variant_id)]
        return ReauditResult(self._narrative_repo.list_claim_ids_for_evidence(evidence_ids))

    async def queue_reaudit_content_variant(
        self,
        variant_id: str,
        *,
        tenant_id: str,
        policy: dict | None = None,
    ) -> ReauditResult:
        if self._task_service is None:
            raise RuntimeError("analysis task service is not configured")
        result = await self.reaudit_content_variant(variant_id)
        task_ids: list[str] = []
        for claim_id in result.reaudited_claim_ids:
            claim = self._narrative_repo.get_claim(claim_id)
            if claim is None:
                continue
            task = self._task_service.queue_reaudit(
                claim=claim,
                tenant_id=tenant_id,
                policy=policy or {},
            )
            task_ids.append(task.id)
        return ReauditResult(result.reaudited_claim_ids, task_ids)
