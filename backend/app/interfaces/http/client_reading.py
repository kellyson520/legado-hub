from fastapi import APIRouter, Depends

from app.core.exceptions import AuthorizationException
from app.core.response import ok
from app.infrastructure.persistence.factory import build_content_distribution_service
from app.interfaces.http.deps import ApiKeyIdentity, get_api_key_identity


router = APIRouter()


def _assert_capability(identity: ApiKeyIdentity, capability: str) -> None:
    if capability not in identity.permissions:
        raise AuthorizationException(f'Permission denied: {capability}')


def _tenant_id(identity: ApiKeyIdentity) -> str:
    return f'api-key:{identity.api_key_id}'


@router.get('/works')
async def list_client_works(identity: ApiKeyIdentity = Depends(get_api_key_identity)):
    _assert_capability(identity, 'read.work')
    data = build_content_distribution_service().list_works(tenant_id=_tenant_id(identity))
    return ok(data=data, message='works listed', meta={'total': len(data)})


@router.get('/works/{work_id}')
async def get_client_work(work_id: str, identity: ApiKeyIdentity = Depends(get_api_key_identity)):
    _assert_capability(identity, 'read.work')
    data = build_content_distribution_service().get_work(tenant_id=_tenant_id(identity), work_id=work_id)
    return ok(data=data, message='work retrieved', meta={})


@router.get('/works/{work_id}/toc')
async def get_client_work_toc(work_id: str, identity: ApiKeyIdentity = Depends(get_api_key_identity)):
    _assert_capability(identity, 'read.toc')
    data = build_content_distribution_service().get_toc(tenant_id=_tenant_id(identity), work_id=work_id)
    return ok(data=data, message='toc retrieved', meta={'total': len(data)})


@router.get('/chapters/{chapter_id}')
async def get_client_chapter(chapter_id: str, identity: ApiKeyIdentity = Depends(get_api_key_identity)):
    _assert_capability(identity, 'read.chapter')
    data = build_content_distribution_service().read_chapter(tenant_id=_tenant_id(identity), chapter_id=chapter_id)
    return ok(data=data['result'], message='chapter retrieved', meta={'route_summary': data['route_summary']})
