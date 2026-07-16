import json
from datetime import datetime
from uuid import uuid4

from app.database import SessionLocal
from app.domain.entities.novel_analysis_task import NovelAnalysisTask

from .schema import AgentAnalysisTaskModel, AgentTaskCheckpointModel, KnowledgeAdjudicationModel


class SQLiteNovelAnalysisTaskRepository:
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    @staticmethod
    def _entity(model: AgentAnalysisTaskModel) -> NovelAnalysisTask:
        return NovelAnalysisTask(
            id=model.id,
            work_id=model.work_id,
            tenant_id=model.tenant_id,
            goal=model.goal,
            status=model.status,
            policy=json.loads(model.policy_json),
            checkpoint=json.loads(model.checkpoint_json),
            tool_call_count=model.tool_call_count,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def create(self, task: NovelAnalysisTask) -> NovelAnalysisTask:
        db = self._db()
        try:
            model = AgentAnalysisTaskModel(
                id=task.id,
                work_id=task.work_id,
                tenant_id=task.tenant_id,
                goal=task.goal,
                status=task.status,
                policy_json=json.dumps(task.policy, ensure_ascii=False),
                checkpoint_json=json.dumps(task.checkpoint, ensure_ascii=False),
                tool_call_count=task.tool_call_count,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._entity(model)
        finally:
            self._close(db)

    def get(self, task_id: str, tenant_id: str) -> NovelAnalysisTask | None:
        db = self._db()
        try:
            model = db.query(AgentAnalysisTaskModel).filter(AgentAnalysisTaskModel.id == task_id, AgentAnalysisTaskModel.tenant_id == tenant_id).first()
            return self._entity(model) if model else None
        finally:
            self._close(db)

    def list_for_work(self, work_id: str, tenant_id: str) -> list[NovelAnalysisTask]:
        db = self._db()
        try:
            models = (
                db.query(AgentAnalysisTaskModel)
                .filter(
                    AgentAnalysisTaskModel.work_id == work_id,
                    AgentAnalysisTaskModel.tenant_id == tenant_id,
                )
                .order_by(AgentAnalysisTaskModel.created_at.desc())
                .all()
            )
            return [self._entity(model) for model in models]
        finally:
            self._close(db)

    def update(self, task: NovelAnalysisTask) -> NovelAnalysisTask:
        db = self._db()
        try:
            model = db.query(AgentAnalysisTaskModel).filter(AgentAnalysisTaskModel.id == task.id, AgentAnalysisTaskModel.tenant_id == task.tenant_id).first()
            if model is None:
                raise LookupError("analysis task not found")
            model.status = task.status
            model.policy_json = json.dumps(task.policy, ensure_ascii=False)
            model.checkpoint_json = json.dumps(task.checkpoint, ensure_ascii=False)
            model.tool_call_count = task.tool_call_count
            model.updated_at = datetime.utcnow()
            db.add(AgentTaskCheckpointModel(id=uuid4().hex, task_id=task.id, checkpoint_json=model.checkpoint_json))
            db.commit()
            db.refresh(model)
            return self._entity(model)
        finally:
            self._close(db)

    def lease_next(self) -> NovelAnalysisTask | None:
        """Atomically transition the oldest queued task to running."""
        db = self._db()
        try:
            candidate = (
                db.query(AgentAnalysisTaskModel.id)
                .filter(AgentAnalysisTaskModel.status == "queued")
                .order_by(AgentAnalysisTaskModel.created_at.asc())
                .first()
            )
            if candidate is None:
                return None
            return self._lease_in_db(db, task_id=candidate[0], tenant_id=None)
        finally:
            self._close(db)

    def lease(self, task_id: str, tenant_id: str) -> NovelAnalysisTask | None:
        db = self._db()
        try:
            return self._lease_in_db(db, task_id=task_id, tenant_id=tenant_id)
        finally:
            self._close(db)

    def _lease_in_db(self, db, *, task_id: str, tenant_id: str | None) -> NovelAnalysisTask | None:
        query = db.query(AgentAnalysisTaskModel).filter(
            AgentAnalysisTaskModel.id == task_id,
            AgentAnalysisTaskModel.status == "queued",
        )
        if tenant_id is not None:
            query = query.filter(AgentAnalysisTaskModel.tenant_id == tenant_id)
        updated = query.update(
            {"status": "running", "updated_at": datetime.utcnow()},
            synchronize_session=False,
        )
        if updated != 1:
            db.rollback()
            return None
        db.add(AgentTaskCheckpointModel(
            id=uuid4().hex,
            task_id=task_id,
            checkpoint_json=json.dumps({"lease": "running"}, ensure_ascii=False),
        ))
        db.commit()
        model = (
            db.query(AgentAnalysisTaskModel)
            .filter(AgentAnalysisTaskModel.id == task_id)
            .first()
        )
        return self._entity(model) if model is not None else None

    def record_adjudication(
        self,
        *,
        claim_id: str,
        tenant_id: str,
        role: str,
        verdict: str,
        reasons: tuple[str, ...],
        evidence_ids: list[str],
        provider_group: str | None,
        provider_name: str | None,
        model: str | None,
        prompt_version: str | None,
        task_id: str | None = None,
        policy: dict | None = None,
    ) -> dict:
        db = self._db()
        try:
            record = KnowledgeAdjudicationModel(
                id=uuid4().hex,
                claim_id=claim_id,
                tenant_id=tenant_id,
                task_id=task_id,
                role=role,
                verdict=verdict,
                reasons_json=json.dumps(list(reasons), ensure_ascii=False),
                evidence_ids_json=json.dumps(list(dict.fromkeys(evidence_ids)), ensure_ascii=False),
                provider_group=provider_group,
                provider_name=provider_name,
                model=model,
                prompt_version=prompt_version,
                policy_json=json.dumps(policy or {}, ensure_ascii=False, sort_keys=True),
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return self._adjudication(record)
        finally:
            self._close(db)

    def list_adjudications(self, claim_id: str, *, tenant_id: str) -> list[dict]:
        db = self._db()
        try:
            records = (
                db.query(KnowledgeAdjudicationModel)
                .filter(
                    KnowledgeAdjudicationModel.claim_id == claim_id,
                    KnowledgeAdjudicationModel.tenant_id == tenant_id,
                )
                .order_by(KnowledgeAdjudicationModel.created_at.asc())
                .all()
            )
            return [self._adjudication(record) for record in records]
        finally:
            self._close(db)

    @staticmethod
    def _adjudication(record: KnowledgeAdjudicationModel) -> dict:
        return {
            "id": record.id,
            "claim_id": record.claim_id,
            "tenant_id": record.tenant_id,
            "task_id": record.task_id,
            "role": record.role,
            "verdict": record.verdict,
            "reasons": json.loads(record.reasons_json or "[]"),
            "evidence_ids": json.loads(record.evidence_ids_json or "[]"),
            "provider_group": record.provider_group,
            "provider_name": record.provider_name,
            "model": record.model,
            "prompt_version": record.prompt_version,
            "policy": json.loads(record.policy_json or "{}"),
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
