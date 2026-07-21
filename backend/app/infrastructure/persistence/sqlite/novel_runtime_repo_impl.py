import json
from uuid import uuid4

from sqlalchemy import or_

from app.core.pagination import LIKE_ESCAPE, like_pattern
from app.infrastructure.persistence.sqlite.session import SessionLocal
from app.domain.entities.novel_runtime import NovelAnalysisTask, NovelIngestion
from app.domain.repositories.novel_runtime_repo import NovelRuntimeRepository

from .schema import NovelIngestionModel, NovelTaskModel


class SQLiteNovelRuntimeRepository(NovelRuntimeRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    def save_ingestion(self, ingestion: NovelIngestion) -> NovelIngestion:
        db = self._db()
        try:
            model = NovelIngestionModel(
                id=ingestion.id or uuid4().hex,
                owner_scope=ingestion.owner_scope,
                book_id=ingestion.book_id,
                title=ingestion.title,
                source_text=ingestion.source_text,
                status=ingestion.status,
                provider=ingestion.provider,
                pipeline=ingestion.pipeline,
            )
            db.merge(model)
            db.commit()
            saved = db.query(NovelIngestionModel).filter(NovelIngestionModel.id == model.id).first()
            return self._to_ingestion(saved)
        finally:
            self._close(db)

    def list_ingestions(self, owner_scope: str | None = None) -> list[NovelIngestion]:
        db = self._db()
        try:
            query = db.query(NovelIngestionModel)
            if owner_scope is not None:
                query = query.filter(NovelIngestionModel.owner_scope == owner_scope)
            rows = query.order_by(NovelIngestionModel.created_at.desc()).all()
            return [self._to_ingestion(row) for row in rows]
        finally:
            self._close(db)

    def list_ingestions_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
        owner_scope: str | None = None,
    ) -> tuple[list[NovelIngestion], int]:
        db = self._db()
        try:
            query = db.query(NovelIngestionModel)
            if owner_scope is not None:
                query = query.filter(NovelIngestionModel.owner_scope == owner_scope)
            if status:
                query = query.filter(NovelIngestionModel.status == status)
            normalized_search = search.strip()
            if normalized_search:
                pattern = like_pattern(normalized_search)
                query = query.filter(
                    or_(
                        NovelIngestionModel.id.ilike(pattern, escape=LIKE_ESCAPE),
                        NovelIngestionModel.title.ilike(pattern, escape=LIKE_ESCAPE),
                        NovelIngestionModel.provider.ilike(pattern, escape=LIKE_ESCAPE),
                        NovelIngestionModel.pipeline.ilike(pattern, escape=LIKE_ESCAPE),
                    )
                )
            total = query.count()
            rows = (
                query.order_by(NovelIngestionModel.created_at.desc(), NovelIngestionModel.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return [self._to_ingestion(row) for row in rows], total
        finally:
            self._close(db)

    def get_ingestion(self, novel_id: str, owner_scope: str | None = None) -> NovelIngestion | None:
        db = self._db()
        try:
            query = db.query(NovelIngestionModel).filter(NovelIngestionModel.id == novel_id)
            if owner_scope is not None:
                query = query.filter(NovelIngestionModel.owner_scope == owner_scope)
            row = query.first()
            return self._to_ingestion(row) if row else None
        finally:
            self._close(db)

    def claim_legacy_scope(self, owner_scope: str) -> dict:
        if not owner_scope or owner_scope == "legacy":
            raise ValueError("legacy scope cannot be claimed by itself")
        db = self._db()
        try:
            ingestion_cursor = db.query(NovelIngestionModel).filter(
                NovelIngestionModel.owner_scope == "legacy"
            ).update({NovelIngestionModel.owner_scope: owner_scope}, synchronize_session=False)
            task_cursor = db.query(NovelTaskModel).filter(
                NovelTaskModel.owner_scope == "legacy"
            ).update({NovelTaskModel.owner_scope: owner_scope}, synchronize_session=False)
            db.commit()
            return {"ingestions": ingestion_cursor, "tasks": task_cursor}
        except Exception:
            db.rollback()
            raise
        finally:
            self._close(db)

    def save_task(self, task: NovelAnalysisTask) -> NovelAnalysisTask:
        db = self._db()
        try:
            model = NovelTaskModel(
                id=task.id or uuid4().hex,
                novel_id=task.novel_id,
                owner_scope=task.owner_scope,
                book_id=task.book_id,
                chapter_id=task.chapter_id,
                actor_id=task.actor_id,
                status=task.status,
                provider_name=task.provider,
                model_name=task.model,
                pipeline=task.pipeline,
                result_payload=json.dumps(task.result, ensure_ascii=False),
                usage_payload=json.dumps(task.usage, ensure_ascii=False),
            )
            model = db.merge(model)
            ingestion = db.query(NovelIngestionModel).filter(NovelIngestionModel.id == task.novel_id).first()
            if ingestion is not None:
                ingestion.status = task.status
                ingestion.provider = task.provider
                ingestion.pipeline = task.pipeline
            db.commit()
            db.refresh(model)
            return self._to_task(model)
        finally:
            self._close(db)

    def list_tasks(self, owner_scope: str | None = None) -> list[NovelAnalysisTask]:
        db = self._db()
        try:
            query = db.query(NovelTaskModel)
            if owner_scope is not None:
                query = query.filter(NovelTaskModel.owner_scope == owner_scope)
            rows = query.order_by(NovelTaskModel.created_at.desc()).all()
            return [self._to_task(row) for row in rows]
        finally:
            self._close(db)

    @staticmethod
    def _to_ingestion(model: NovelIngestionModel) -> NovelIngestion:
        return NovelIngestion(
            id=model.id,
            owner_scope=model.owner_scope,
            book_id=model.book_id,
            title=model.title,
            source_text=model.source_text,
            status=model.status,
            provider=model.provider,
            pipeline=model.pipeline,
            created_at=model.created_at,
        )

    @staticmethod
    def _to_task(model: NovelTaskModel) -> NovelAnalysisTask:
        return NovelAnalysisTask(
            id=model.id,
            owner_scope=model.owner_scope,
            novel_id=model.novel_id,
            book_id=model.book_id,
            chapter_id=model.chapter_id,
            actor_id=model.actor_id,
            status=model.status,
            provider=model.provider_name,
            model=model.model_name,
            pipeline=model.pipeline,
            result=json.loads(model.result_payload),
            usage=json.loads(model.usage_payload),
            created_at=model.created_at,
        )
