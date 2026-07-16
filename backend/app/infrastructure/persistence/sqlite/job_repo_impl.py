import json
from datetime import timedelta, timezone
from uuid import uuid4

from sqlalchemy import or_

from app.database import SessionLocal
from app.domain.entities.job import Job, JobEvent

from .schema import JobEventModel, JobModel


class SQLiteJobRepository:
    @staticmethod
    def _entity(model: JobModel) -> Job:
        def utc(value):
            return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value

        return Job(
            id=model.id,
            kind=model.kind,
            tenant_id=model.tenant_id,
            payload=json.loads(model.payload),
            idempotency_key=model.idempotency_key,
            status=model.status,
            attempt_count=model.attempt_count,
            worker_id=model.worker_id,
            lease_token=model.lease_token,
            lease_expires_at=utc(model.lease_expires_at),
            available_at=utc(model.available_at),
            last_error=model.last_error,
            created_at=utc(model.created_at),
        )

    def get_by_idempotency_key(self, tenant_id: str, idempotency_key: str) -> Job | None:
        db = SessionLocal()
        try:
            model = db.query(JobModel).filter(JobModel.tenant_id == tenant_id, JobModel.idempotency_key == idempotency_key).first()
            return self._entity(model) if model else None
        finally:
            db.close()

    def save(self, job: Job) -> Job:
        db = SessionLocal()
        try:
            model = JobModel(id=job.id, kind=job.kind, tenant_id=job.tenant_id, payload=json.dumps(job.payload), idempotency_key=job.idempotency_key)
            db.add(model)
            db.add(JobEventModel(job_id=job.id, tenant_id=job.tenant_id, event_type='queued', detail='{}'))
            db.commit()
            db.refresh(model)
            return self._entity(model)
        finally:
            db.close()

    def get(self, job_id: str) -> Job | None:
        db = SessionLocal()
        try:
            model = db.query(JobModel).filter(JobModel.id == job_id).first()
            return self._entity(model) if model else None
        finally:
            db.close()

    def list_jobs(self) -> list[Job]:
        db = SessionLocal()
        try:
            models = db.query(JobModel).order_by(JobModel.created_at.desc(), JobModel.id.desc()).all()
            return [self._entity(model) for model in models]
        finally:
            db.close()

    def list_jobs_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
    ) -> tuple[list[Job], int]:
        db = SessionLocal()
        try:
            query = db.query(JobModel)
            if status:
                query = query.filter(JobModel.status == status)
            normalized_search = search.strip()
            if normalized_search:
                pattern = f"%{normalized_search}%"
                query = query.filter(
                    or_(
                        JobModel.id.ilike(pattern),
                        JobModel.kind.ilike(pattern),
                        JobModel.tenant_id.ilike(pattern),
                    )
                )
            total = query.count()
            models = (
                query.order_by(JobModel.created_at.desc(), JobModel.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return [self._entity(model) for model in models], total
        finally:
            db.close()

    def finish(
        self,
        *,
        job_id: str,
        worker_id: str,
        lease_token: str,
        now,
        status: str,
        error: str | None,
        available_at,
        event_type: str,
        event_detail: dict,
    ) -> Job:
        db = SessionLocal()
        try:
            updated = (
                db.query(JobModel)
                .filter(
                    JobModel.id == job_id,
                    JobModel.status == 'leased',
                    JobModel.worker_id == worker_id,
                    JobModel.lease_token == lease_token,
                    JobModel.lease_expires_at >= now,
                )
                .update(
                    {
                        JobModel.status: status,
                        JobModel.last_error: error,
                        JobModel.worker_id: None,
                        JobModel.lease_token: None,
                        JobModel.lease_expires_at: None,
                        JobModel.available_at: available_at,
                    },
                    synchronize_session=False,
                )
            )
            if updated != 1:
                db.rollback()
                raise PermissionError('Job lease is not held by this worker')
            model = db.query(JobModel).filter(JobModel.id == job_id).one()
            db.add(
                JobEventModel(
                    job_id=model.id,
                    tenant_id=model.tenant_id,
                    event_type=event_type,
                    detail=json.dumps(event_detail),
                )
            )
            db.commit()
            db.refresh(model)
            return self._entity(model)
        finally:
            db.close()

    def lease_next(self, *, worker_id: str, now, lease_seconds: int) -> Job | None:
        db = SessionLocal()
        try:
            claimable = (
                ((JobModel.status == 'queued') & ((JobModel.available_at.is_(None)) | (JobModel.available_at <= now)))
                | ((JobModel.status == 'leased') & (JobModel.lease_expires_at < now))
            )
            candidate = (
                db.query(JobModel)
                .filter(claimable)
                .order_by(JobModel.created_at.asc())
                .first()
            )
            if candidate is None:
                return None
            updated = (
                db.query(JobModel)
                .filter(JobModel.id == candidate.id, claimable)
                .update(
                    {
                        JobModel.status: 'leased',
                        JobModel.worker_id: worker_id,
                        JobModel.lease_token: uuid4().hex,
                        JobModel.attempt_count: JobModel.attempt_count + 1,
                        JobModel.lease_expires_at: now + timedelta(seconds=lease_seconds),
                        JobModel.available_at: None,
                    },
                    synchronize_session=False,
                )
            )
            if updated != 1:
                db.rollback()
                return None
            model = db.query(JobModel).filter(JobModel.id == candidate.id).one()
            db.add(
                JobEventModel(
                    job_id=model.id,
                    tenant_id=model.tenant_id,
                    event_type='leased',
                    detail=json.dumps({'worker_id': worker_id, 'attempt_count': model.attempt_count}),
                )
            )
            db.commit()
            db.refresh(model)
            return self._entity(model)
        finally:
            db.close()

    def renew_lease(self, *, job_id: str, worker_id: str, lease_token: str, now, lease_seconds: int) -> Job:
        db = SessionLocal()
        try:
            lease_expires_at = now + timedelta(seconds=lease_seconds)
            updated = (
                db.query(JobModel)
                .filter(
                    JobModel.id == job_id,
                    JobModel.status == 'leased',
                    JobModel.worker_id == worker_id,
                    JobModel.lease_token == lease_token,
                    JobModel.lease_expires_at >= now,
                )
                .update({JobModel.lease_expires_at: lease_expires_at}, synchronize_session=False)
            )
            if updated != 1:
                db.rollback()
                raise PermissionError('Job lease is not held by this worker')
            model = db.query(JobModel).filter(JobModel.id == job_id).one()
            db.add(
                JobEventModel(
                    job_id=model.id,
                    tenant_id=model.tenant_id,
                    event_type='lease_renewed',
                    detail=json.dumps({'worker_id': worker_id}),
                )
            )
            db.commit()
            db.refresh(model)
            return self._entity(model)
        finally:
            db.close()

    def list_events(self, job_id: str) -> list[JobEvent]:
        db = SessionLocal()
        try:
            models = (
                db.query(JobEventModel)
                .filter(JobEventModel.job_id == job_id)
                .order_by(JobEventModel.created_at.asc(), JobEventModel.id.asc())
                .all()
            )
            return [
                JobEvent(
                    id=model.id,
                    job_id=model.job_id,
                    tenant_id=model.tenant_id,
                    event_type=model.event_type,
                    detail=json.loads(model.detail),
                    created_at=model.created_at.replace(tzinfo=timezone.utc) if model.created_at.tzinfo is None else model.created_at,
                )
                for model in models
            ]
        finally:
            db.close()
