from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.domain.entities.job import Job
from sqlalchemy.exc import IntegrityError


class JobService:
    RETRY_BASE_SECONDS = 30

    def __init__(self, repo):
        self._repo = repo

    def enqueue(self, *, kind: str, tenant_id: str, payload: dict, idempotency_key: str | None = None) -> Job:
        if idempotency_key:
            existing = self._repo.get_by_idempotency_key(tenant_id, idempotency_key)
            if existing is not None:
                return existing
        try:
            return self._repo.save(Job(id=uuid4().hex, kind=kind, tenant_id=tenant_id, payload=payload, idempotency_key=idempotency_key))
        except IntegrityError:
            existing = self._repo.get_by_idempotency_key(tenant_id, idempotency_key)
            if existing is not None:
                return existing
            raise

    def lease_next(self, *, worker_id: str, now: datetime | None = None, lease_seconds: int = 60) -> Job | None:
        moment = now or datetime.now(timezone.utc)
        return self._repo.lease_next(worker_id=worker_id, now=moment.replace(tzinfo=None), lease_seconds=lease_seconds)

    def renew_lease(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        now: datetime | None = None,
        lease_seconds: int = 60,
    ) -> Job:
        moment = (now or datetime.now(timezone.utc)).replace(tzinfo=None)
        return self._repo.renew_lease(
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            now=moment,
            lease_seconds=lease_seconds,
        )

    def complete(self, job_id: str, *, worker_id: str, lease_token: str, now: datetime | None = None) -> Job:
        return self._repo.finish(
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            now=(now or datetime.now(timezone.utc)).replace(tzinfo=None),
            status='succeeded',
            error=None,
            available_at=None,
            event_type='succeeded',
            event_detail={},
        )

    def get(self, job_id: str, *, tenant_id: str) -> Job | None:
        job = self._repo.get(job_id)
        return job if job is not None and job.tenant_id == tenant_id else None

    def list_jobs(self) -> list[Job]:
        return self._repo.list_jobs()

    def list_events(self, job_id: str, *, tenant_id: str):
        if self.get(job_id, tenant_id=tenant_id) is None:
            return None
        return self._repo.list_events(job_id)

    def fail(
        self,
        job_id: str,
        *,
        error: str,
        worker_id: str,
        lease_token: str,
        max_attempts: int = 3,
        now: datetime | None = None,
    ) -> Job:
        job = self._repo.get(job_id)
        if job is None:
            raise LookupError(f'job not found: {job_id}')
        status = 'dead_letter' if job.attempt_count >= max_attempts else 'queued'
        available_at = None
        if status == 'queued':
            moment = now or datetime.now(timezone.utc)
            delay_seconds = self.RETRY_BASE_SECONDS * (2 ** max(job.attempt_count - 1, 0))
            available_at = moment.replace(tzinfo=None) + timedelta(seconds=delay_seconds)
        return self._repo.finish(
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            now=(now or datetime.now(timezone.utc)).replace(tzinfo=None),
            status=status,
            error=error,
            available_at=available_at,
            event_type='dead_letter' if status == 'dead_letter' else 'retrying',
            event_detail={
                'error': error,
                'available_at': available_at.isoformat() if available_at is not None else None,
            },
        )
