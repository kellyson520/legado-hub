import json
from uuid import uuid4

from sqlalchemy import or_

from app.core.pagination import LIKE_ESCAPE, like_pattern
from app.database import SessionLocal
from app.domain.entities.ai_runtime import AITask
from app.domain.repositories.ai_runtime_repo import AIRuntimeRepository

from .schema import AITaskModel


class SQLiteAIRuntimeRepository(AIRuntimeRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    def save_task(self, task: AITask) -> AITask:
        db = self._db()
        try:
            model = AITaskModel(
                id=task.id or uuid4().hex,
                task_type=task.kind,
                actor_id=task.actor_id,
                provider_name=task.provider,
                model_name=task.model,
                status=task.status,
                prompt_payload=json.dumps(task.prompt_payload, ensure_ascii=False),
                result_payload=json.dumps(task.result, ensure_ascii=False),
                usage_payload=json.dumps(task.usage, ensure_ascii=False),
                cost_payload=json.dumps(task.cost, ensure_ascii=False),
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._to_entity(model)
        finally:
            self._close(db)

    def list_tasks(self) -> list[AITask]:
        db = self._db()
        try:
            rows = db.query(AITaskModel).order_by(AITaskModel.created_at.desc()).all()
            return [self._to_entity(row) for row in rows]
        finally:
            self._close(db)

    def list_tasks_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
    ) -> tuple[list[AITask], int]:
        db = self._db()
        try:
            query = db.query(AITaskModel)
            if status:
                query = query.filter(AITaskModel.status == status)
            normalized_search = search.strip()
            if normalized_search:
                pattern = like_pattern(normalized_search)
                query = query.filter(
                    or_(
                        AITaskModel.id.ilike(pattern, escape=LIKE_ESCAPE),
                        AITaskModel.task_type.ilike(pattern, escape=LIKE_ESCAPE),
                        AITaskModel.actor_id.ilike(pattern, escape=LIKE_ESCAPE),
                        AITaskModel.provider_name.ilike(pattern, escape=LIKE_ESCAPE),
                        AITaskModel.model_name.ilike(pattern, escape=LIKE_ESCAPE),
                    )
                )
            total = query.count()
            rows = (
                query.order_by(AITaskModel.created_at.desc(), AITaskModel.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return [self._to_entity(row) for row in rows], total
        finally:
            self._close(db)

    @staticmethod
    def _to_entity(model: AITaskModel) -> AITask:
        return AITask(
            id=model.id,
            kind=model.task_type,
            actor_id=model.actor_id,
            provider=model.provider_name,
            model=model.model_name,
            status=model.status,
            prompt_payload=json.loads(model.prompt_payload),
            result=json.loads(model.result_payload),
            usage=json.loads(model.usage_payload),
            cost=json.loads(model.cost_payload),
            created_at=model.created_at,
        )
