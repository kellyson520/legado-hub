from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from app.core.response import ok
from app.infrastructure.persistence.factory import build_job_service
from app.interfaces.http.deps import ApiKeyIdentity, get_api_key_identity


router = APIRouter()


class SubmitJobRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=120)
    payload: dict = Field(default_factory=dict)


@router.post('/jobs')
async def submit_job(
    payload: SubmitJobRequest,
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
    identity: ApiKeyIdentity = Depends(get_api_key_identity),
):
    if 'jobs.submit' not in identity.permissions:
        from app.core.exceptions import AuthorizationException
        raise AuthorizationException('Permission denied: jobs.submit')
    job = build_job_service().enqueue(
        kind=payload.kind,
        tenant_id=f'api-key:{identity.api_key_id}',
        payload=payload.payload,
        idempotency_key=idempotency_key,
    )
    return ok(data={'job_id': job.id, 'status': job.status}, message='job accepted', meta={})


@router.get('/jobs/{job_id}')
async def get_job(job_id: str, identity: ApiKeyIdentity = Depends(get_api_key_identity)):
    service = build_job_service()
    job = service.get(job_id, tenant_id=f'api-key:{identity.api_key_id}')
    if job is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail='Job not found')
    if 'events.read' not in identity.permissions:
        from app.core.exceptions import AuthorizationException
        raise AuthorizationException('Permission denied: events.read')
    return ok(
        data={
            'job_id': job.id,
            'kind': job.kind,
            'status': job.status,
            'attempt_count': job.attempt_count,
            'last_error': job.last_error,
            'events': [
                {
                    'id': event.id,
                    'type': event.event_type,
                    'detail': event.detail,
                    'created_at': event.created_at.isoformat() if event.created_at is not None else None,
                }
                for event in service.list_events(job_id, tenant_id=f'api-key:{identity.api_key_id}') or []
            ],
        },
        message='job retrieved',
        meta={},
    )
