import json

from app.database import SessionLocal
from app.domain.entities.work_knowledge import WorkKnowledgeProposal

from .schema import WorkKnowledgeProposalModel


class SQLiteWorkKnowledgeRepository:
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    @staticmethod
    def _entity(model: WorkKnowledgeProposalModel) -> WorkKnowledgeProposal:
        return WorkKnowledgeProposal(
            id=model.id,
            work_id=model.work_id,
            source_chapter_id=model.source_chapter_id,
            proposal_type=model.proposal_type,
            subject=model.subject,
            relation=model.relation,
            object_name=model.object_name,
            evidence=model.evidence,
            payload=json.loads(model.payload_json) if model.payload_json else {},
            status=model.status,
            revision_of=model.revision_of,
            created_by=model.created_by,
            reviewed_by=model.reviewed_by,
            created_at=model.created_at,
            published_at=model.published_at,
        )

    def save_proposal(self, proposal: WorkKnowledgeProposal) -> WorkKnowledgeProposal:
        db = self._db()
        try:
            model = WorkKnowledgeProposalModel(
                id=proposal.id,
                work_id=proposal.work_id,
                source_chapter_id=proposal.source_chapter_id,
                proposal_type=proposal.proposal_type,
                subject=proposal.subject,
                relation=proposal.relation,
                object_name=proposal.object_name,
                evidence=proposal.evidence,
                payload_json=json.dumps(proposal.payload, ensure_ascii=False),
                status=proposal.status,
                revision_of=proposal.revision_of,
                created_by=proposal.created_by,
                reviewed_by=proposal.reviewed_by,
                created_at=proposal.created_at,
                published_at=proposal.published_at,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._entity(model)
        finally:
            self._close(db)

    def get_proposal(self, proposal_id: str) -> WorkKnowledgeProposal | None:
        db = self._db()
        try:
            model = db.query(WorkKnowledgeProposalModel).filter(WorkKnowledgeProposalModel.id == proposal_id).first()
            return self._entity(model) if model else None
        finally:
            self._close(db)

    def list_proposals(
        self,
        *,
        work_id: str | None = None,
        proposal_type: str | None = None,
        status: str | None = None,
    ) -> list[WorkKnowledgeProposal]:
        db = self._db()
        try:
            query = db.query(WorkKnowledgeProposalModel)
            if work_id is not None:
                query = query.filter(WorkKnowledgeProposalModel.work_id == work_id)
            if proposal_type is not None:
                query = query.filter(WorkKnowledgeProposalModel.proposal_type == proposal_type)
            if status is not None:
                query = query.filter(WorkKnowledgeProposalModel.status == status)
            rows = query.order_by(WorkKnowledgeProposalModel.created_at.asc()).all()
            return [self._entity(row) for row in rows]
        finally:
            self._close(db)
