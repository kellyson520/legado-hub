from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.exceptions import AuthorizationException
from app.core.response import ok
from app.infrastructure.persistence.factory import build_source_build_service
from app.interfaces.http.deps import ApiKeyIdentity, get_api_key_identity


router = APIRouter()


class SourceBuildRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    keyword: str = Field(default='', max_length=200)


def _assert_source_submit(identity: ApiKeyIdentity) -> None:
    if 'source.submit' not in identity.permissions:
        raise AuthorizationException('Permission denied: source.submit')


@router.post('/source-builds')
async def submit_source_build(
    payload: SourceBuildRequest,
    identity: ApiKeyIdentity = Depends(get_api_key_identity),
):
    _assert_source_submit(identity)
    submission = build_source_build_service().submit(
        tenant_id=f'api-key:{identity.api_key_id}',
        url=payload.url,
        keyword=payload.keyword,
    )
    return ok(
        data={
            'job_id': submission.job_id,
            'normalized_url': submission.normalized_url,
            'status': submission.status,
            'source_version_id': submission.source_version_id,
            'source_version_status': submission.source_version_status,
        },
        message='source build accepted',
        meta={},
    )
