import json
from uuid import uuid4

from sqlalchemy import or_

from app.database import SessionLocal
from app.core.pagination import LIKE_ESCAPE, like_pattern
from app.domain.entities.translation_runtime import TranslationChunk, TranslationJob
from app.domain.repositories.translation_runtime_repo import TranslationRuntimeRepository

from .schema import TranslationChunkModel, TranslationTaskModel


class SQLiteTranslationRuntimeRepository(TranslationRuntimeRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    def save_job(self, job: TranslationJob) -> TranslationJob:
        db = self._db()
        try:
            task_model = TranslationTaskModel(
                id=job.id or uuid4().hex,
                actor_id=job.actor_id,
                source_language=job.source_language,
                target_language=job.target_language,
                status=job.status,
                provider_name=job.provider,
                model_name=job.model,
                source_text=job.source_text,
                result_text=job.result_text,
                content_variant_id=job.content_variant_id,
                review_status=job.review_status,
                memory_payload=json.dumps(job.memory_payload, ensure_ascii=False),
                chunk_count=job.chunk_count or len(job.chunks),
            )
            db.add(task_model)
            for chunk in job.chunks:
                db.add(
                    TranslationChunkModel(
                        id=chunk.id or uuid4().hex,
                        task_id=task_model.id,
                        chunk_index=chunk.chunk_index,
                        source_text=chunk.source_text,
                        translated_text=chunk.translated_text,
                        status=chunk.status,
                        provider_name=chunk.provider,
                        model_name=chunk.model,
                        usage_payload=json.dumps(chunk.usage, ensure_ascii=False),
                        attempt_count=chunk.attempt_count,
                    )
                )
            db.commit()
            db.refresh(task_model)
            return self._load_job(db, task_model)
        finally:
            self._close(db)

    def list_jobs(self) -> list[TranslationJob]:
        db = self._db()
        try:
            tasks = db.query(TranslationTaskModel).order_by(TranslationTaskModel.created_at.desc()).all()
            return [self._load_job(db, task) for task in tasks]
        finally:
            self._close(db)

    def list_jobs_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
        review_status: str | None = None,
    ) -> tuple[list[TranslationJob], int]:
        db = self._db()
        try:
            query = db.query(TranslationTaskModel)
            if status:
                query = query.filter(TranslationTaskModel.status == status)
            if review_status:
                query = query.filter(TranslationTaskModel.review_status == review_status)
            normalized_search = search.strip()
            if normalized_search:
                pattern = like_pattern(normalized_search)
                query = query.filter(
                    or_(
                        TranslationTaskModel.id.ilike(pattern, escape=LIKE_ESCAPE),
                        TranslationTaskModel.actor_id.ilike(pattern, escape=LIKE_ESCAPE),
                        TranslationTaskModel.source_language.ilike(pattern, escape=LIKE_ESCAPE),
                        TranslationTaskModel.target_language.ilike(pattern, escape=LIKE_ESCAPE),
                        TranslationTaskModel.provider_name.ilike(pattern, escape=LIKE_ESCAPE),
                        TranslationTaskModel.model_name.ilike(pattern, escape=LIKE_ESCAPE),
                        TranslationTaskModel.source_text.ilike(pattern, escape=LIKE_ESCAPE),
                        TranslationTaskModel.result_text.ilike(pattern, escape=LIKE_ESCAPE),
                        TranslationTaskModel.content_variant_id.ilike(pattern, escape=LIKE_ESCAPE),
                        TranslationTaskModel.memory_payload.ilike(pattern, escape=LIKE_ESCAPE),
                    )
                )
            total = query.count()
            tasks = (
                query.order_by(TranslationTaskModel.created_at.desc(), TranslationTaskModel.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return [self._load_job(db, task) for task in tasks], total
        finally:
            self._close(db)

    def get_job(self, job_id: str) -> TranslationJob | None:
        db = self._db()
        try:
            task = db.query(TranslationTaskModel).filter(TranslationTaskModel.id == job_id).first()
            return self._load_job(db, task) if task else None
        finally:
            self._close(db)

    def update_job_review(self, job_id: str, *, review_status: str, memory_payload: dict) -> TranslationJob:
        db = self._db()
        try:
            task = db.query(TranslationTaskModel).filter(TranslationTaskModel.id == job_id).first()
            if task is None:
                raise KeyError(job_id)
            task.review_status = review_status
            task.memory_payload = json.dumps(memory_payload, ensure_ascii=False)
            db.commit()
            db.refresh(task)
            return self._load_job(db, task)
        finally:
            self._close(db)

    def _load_job(self, db, task_model: TranslationTaskModel) -> TranslationJob:
        chunk_rows = (
            db.query(TranslationChunkModel)
            .filter(TranslationChunkModel.task_id == task_model.id)
            .order_by(TranslationChunkModel.chunk_index.asc())
            .all()
        )
        chunks = [
            TranslationChunk(
                id=row.id,
                job_id=row.task_id,
                chunk_index=row.chunk_index,
                source_text=row.source_text,
                translated_text=row.translated_text,
                status=row.status,
                provider=row.provider_name,
                model=row.model_name,
                usage=json.loads(row.usage_payload),
                attempt_count=row.attempt_count,
                created_at=row.created_at,
            )
            for row in chunk_rows
        ]
        return TranslationJob(
            id=task_model.id,
            actor_id=task_model.actor_id,
            source_language=task_model.source_language,
            target_language=task_model.target_language,
            status=task_model.status,
            provider=task_model.provider_name,
            model=task_model.model_name,
            source_text=task_model.source_text,
            result_text=task_model.result_text,
            content_variant_id=getattr(task_model, 'content_variant_id', None),
            review_status=getattr(task_model, 'review_status', 'candidate'),
            memory_payload=json.loads(getattr(task_model, 'memory_payload', '{}') or '{}'),
            chunk_count=task_model.chunk_count,
            chunks=chunks,
            created_at=task_model.created_at,
        )
