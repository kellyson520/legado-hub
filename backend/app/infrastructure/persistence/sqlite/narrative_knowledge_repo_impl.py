import json
from datetime import datetime
from uuid import uuid4

from app.database import SessionLocal
from app.domain.entities.narrative_knowledge import KnowledgeClaim, KnowledgeConflict, KnowledgeEntity

from .schema import ClaimEvidenceModel, KnowledgeClaimModel, KnowledgeConflictModel, KnowledgeEntityModel


class SQLiteNarrativeKnowledgeRepository:
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db) -> None:
        if self._session is None:
            db.close()

    @staticmethod
    def _entity(model: KnowledgeEntityModel) -> KnowledgeEntity:
        return KnowledgeEntity(
            id=model.id,
            work_id=model.work_id,
            name=model.name,
            entity_type=model.entity_type,
            created_at=model.created_at,
        )

    @staticmethod
    def _claim(model: KnowledgeClaimModel, evidence_ids: list[str]) -> KnowledgeClaim:
        return KnowledgeClaim(
            id=model.id,
            work_id=model.work_id,
            subject_entity_id=model.subject_entity_id,
            predicate=model.predicate,
            object_entity_id=model.object_entity_id,
            scalar_value=json.loads(model.scalar_json) if model.scalar_json is not None else None,
            epistemic=model.epistemic,
            status=model.status,
            evidence_ids=evidence_ids,
            created_at=model.created_at,
            published_at=model.published_at,
        )

    @staticmethod
    def _conflict(model: KnowledgeConflictModel) -> KnowledgeConflict:
        return KnowledgeConflict(
            id=model.id,
            work_id=model.work_id,
            incumbent_claim_id=model.incumbent_claim_id,
            conflicting_claim_id=model.conflicting_claim_id,
            status=model.status,
            created_at=model.created_at,
        )

    def ensure_entity(self, *, entity_id: str, work_id: str, name: str, entity_type: str = "character") -> KnowledgeEntity:
        db = self._db()
        try:
            model = db.query(KnowledgeEntityModel).filter(KnowledgeEntityModel.id == entity_id).first()
            if model is None:
                model = KnowledgeEntityModel(id=entity_id, work_id=work_id, name=name, entity_type=entity_type)
                db.add(model)
                db.commit()
                db.refresh(model)
            return self._entity(model)
        finally:
            self._close(db)

    def create_claim(self, claim: KnowledgeClaim) -> KnowledgeClaim:
        db = self._db()
        try:
            model = KnowledgeClaimModel(
                id=claim.id,
                work_id=claim.work_id,
                subject_entity_id=claim.subject_entity_id,
                predicate=claim.predicate,
                object_entity_id=claim.object_entity_id,
                scalar_json=json.dumps(claim.scalar_value, ensure_ascii=False) if claim.scalar_value is not None else None,
                epistemic=claim.epistemic,
                status=claim.status,
                published_at=claim.published_at,
            )
            db.add(model)
            db.add_all([
                ClaimEvidenceModel(id=uuid4().hex, claim_id=claim.id, evidence_span_id=evidence_id)
                for evidence_id in claim.evidence_ids
            ])
            db.commit()
            db.refresh(model)
            return self._claim(model, list(claim.evidence_ids))
        finally:
            self._close(db)

    def get_claim(self, claim_id: str) -> KnowledgeClaim | None:
        db = self._db()
        try:
            model = db.query(KnowledgeClaimModel).filter(KnowledgeClaimModel.id == claim_id).first()
            if model is None:
                return None
            evidence_ids = [
                row.evidence_span_id
                for row in db.query(ClaimEvidenceModel)
                .filter(ClaimEvidenceModel.claim_id == claim_id)
                .order_by(ClaimEvidenceModel.created_at.asc())
                .all()
            ]
            return self._claim(model, evidence_ids)
        finally:
            self._close(db)

    def update_claim_status(self, claim_id: str, status: str) -> KnowledgeClaim:
        db = self._db()
        try:
            model = db.query(KnowledgeClaimModel).filter(KnowledgeClaimModel.id == claim_id).first()
            if model is None:
                raise LookupError("knowledge claim not found")
            model.status = status
            if status == "published":
                model.published_at = datetime.utcnow()
            db.commit()
            db.refresh(model)
            evidence_ids = [row.evidence_span_id for row in db.query(ClaimEvidenceModel).filter(ClaimEvidenceModel.claim_id == claim_id).all()]
            return self._claim(model, evidence_ids)
        finally:
            self._close(db)

    def list_related_claims(self, claim: KnowledgeClaim) -> list[KnowledgeClaim]:
        db = self._db()
        try:
            models = (
                db.query(KnowledgeClaimModel)
                .filter(
                    KnowledgeClaimModel.work_id == claim.work_id,
                    KnowledgeClaimModel.subject_entity_id == claim.subject_entity_id,
                    KnowledgeClaimModel.predicate == claim.predicate,
                    KnowledgeClaimModel.id != claim.id,
                )
                .all()
            )
            result = []
            for model in models:
                evidence_ids = [row.evidence_span_id for row in db.query(ClaimEvidenceModel).filter(ClaimEvidenceModel.claim_id == model.id).all()]
                result.append(self._claim(model, evidence_ids))
            return result
        finally:
            self._close(db)

    def create_conflict(self, *, work_id: str, incumbent_claim_id: str, conflicting_claim_id: str) -> KnowledgeConflict:
        db = self._db()
        try:
            model = (
                db.query(KnowledgeConflictModel)
                .filter(
                    KnowledgeConflictModel.incumbent_claim_id == incumbent_claim_id,
                    KnowledgeConflictModel.conflicting_claim_id == conflicting_claim_id,
                )
                .first()
            )
            if model is None:
                model = KnowledgeConflictModel(
                    id=uuid4().hex,
                    work_id=work_id,
                    incumbent_claim_id=incumbent_claim_id,
                    conflicting_claim_id=conflicting_claim_id,
                    status="open",
                )
                db.add(model)
                db.commit()
                db.refresh(model)
            return self._conflict(model)
        finally:
            self._close(db)
