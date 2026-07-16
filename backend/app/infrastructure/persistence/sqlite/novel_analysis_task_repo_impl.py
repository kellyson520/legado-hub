import json
from datetime import datetime
from uuid import uuid4

from app.database import SessionLocal
from app.domain.entities.novel_analysis_task import NovelAnalysisTask

from .schema import AgentAnalysisTaskModel, AgentTaskCheckpointModel


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
