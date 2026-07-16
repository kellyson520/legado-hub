from uuid import uuid4

from app.domain.entities.narrative_knowledge import KnowledgeClaim, Publishability


class NarrativeKnowledgeService:
    _EPISTEMIC = {"explicit", "inferred", "speculative"}

    def __init__(self, repo, evidence_service):
        self._repo = repo
        self._evidence_service = evidence_service

    def create_claim(
        self,
        work_id: str,
        subject_entity_id: str,
        predicate: str,
        *,
        object_entity_id: str | None = None,
        scalar_value=None,
        epistemic: str,
        evidence_ids: list[str],
    ) -> KnowledgeClaim:
        if epistemic not in self._EPISTEMIC:
            raise ValueError("unsupported epistemic state")
        verified_ids = self._verified_evidence_ids(evidence_ids)
        self._repo.ensure_entity(entity_id=subject_entity_id, work_id=work_id, name=subject_entity_id)
        if object_entity_id:
            self._repo.ensure_entity(entity_id=object_entity_id, work_id=work_id, name=object_entity_id)
        return self._repo.create_claim(KnowledgeClaim(
            id=uuid4().hex,
            work_id=work_id,
            subject_entity_id=subject_entity_id,
            predicate=predicate,
            object_entity_id=object_entity_id,
            scalar_value=scalar_value,
            epistemic=epistemic,
            evidence_ids=verified_ids,
        ))

    def get_claim(self, claim_id: str) -> KnowledgeClaim | None:
        return self._repo.get_claim(claim_id)

    def publishability(self, claim_id: str) -> Publishability:
        claim = self._require_claim(claim_id)
        verified = self._verified_evidence_ids(claim.evidence_ids)
        if len(verified) != len(set(claim.evidence_ids)):
            return Publishability(False, ("evidence is no longer verified",))
        if claim.epistemic == "speculative":
            return Publishability(False, ("speculative claims require human review",))
        minimum = 2 if claim.epistemic == "inferred" else 1
        if len(verified) < minimum:
            return Publishability(False, (f"{claim.epistemic} claims require {minimum} verified evidence spans",))
        return Publishability(True)

    def publish_claim(self, claim_id: str, *, actor_id: str) -> KnowledgeClaim:
        publishability = self.publishability(claim_id)
        if not publishability.allowed:
            raise ValueError("; ".join(publishability.reasons))
        return self._repo.update_claim_status(claim_id, "published")

    def detect_conflicts(self, claim_id: str):
        claim = self._require_claim(claim_id)
        for related in self._repo.list_related_claims(claim):
            if related.status != "published" or not self._contradicts(claim, related):
                continue
            return self._repo.create_conflict(
                work_id=claim.work_id,
                incumbent_claim_id=related.id,
                conflicting_claim_id=claim.id,
            )
        return None

    def build_work_snapshot(self, work_id: str, *, chapter_limit: int) -> dict:
        return {
            "work_id": work_id,
            "chapter_limit": chapter_limit,
            "published_claims": [
                self._serialize_claim(claim)
                for claim in self._repo.list_claims(work_id=work_id, status="published")
            ],
            "open_conflicts": [
                {
                    "id": conflict.id,
                    "incumbent_claim_id": conflict.incumbent_claim_id,
                    "conflicting_claim_id": conflict.conflicting_claim_id,
                    "status": conflict.status,
                }
                for conflict in self._repo.list_conflicts(work_id=work_id, status="open")
            ],
        }

    def _verified_evidence_ids(self, evidence_ids: list[str]) -> list[str]:
        verified = []
        for evidence_id in dict.fromkeys(evidence_ids):
            if self._evidence_service.get_verified_span(evidence_id) is not None:
                verified.append(evidence_id)
        return verified

    def _require_claim(self, claim_id: str) -> KnowledgeClaim:
        claim = self._repo.get_claim(claim_id)
        if claim is None:
            raise LookupError("knowledge claim not found")
        return claim

    @staticmethod
    def _contradicts(left: KnowledgeClaim, right: KnowledgeClaim) -> bool:
        if left.scalar_value is not None or right.scalar_value is not None:
            return left.scalar_value != right.scalar_value
        return left.object_entity_id != right.object_entity_id

    @staticmethod
    def _serialize_claim(claim: KnowledgeClaim) -> dict:
        return {
            "id": claim.id,
            "subject_entity_id": claim.subject_entity_id,
            "predicate": claim.predicate,
            "object_entity_id": claim.object_entity_id,
            "scalar_value": claim.scalar_value,
            "epistemic": claim.epistemic,
            "status": claim.status,
            "evidence_ids": claim.evidence_ids,
        }
