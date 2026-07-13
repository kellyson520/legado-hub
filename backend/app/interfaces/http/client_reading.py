from fastapi import APIRouter, Depends

from app.core.exceptions import AuthorizationException
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
    return {
        'success': True,
        'code': 'OK',
        'message': 'works listed',
        'data': data,
        'meta': {'total': len(data)},
        'trace_id': None,
    }


@router.get('/works/{work_id}')
async def get_client_work(work_id: str, identity: ApiKeyIdentity = Depends(get_api_key_identity)):
    _assert_capability(identity, 'read.work')
    data = build_content_distribution_service().get_work(tenant_id=_tenant_id(identity), work_id=work_id)
    return {
        'success': True,
        'code': 'OK',
        'message': 'work retrieved',
        'data': data,
        'meta': {},
        'trace_id': None,
    }


@router.get('/works/{work_id}/toc')
async def get_client_work_toc(work_id: str, identity: ApiKeyIdentity = Depends(get_api_key_identity)):
    _assert_capability(identity, 'read.toc')
    data = build_content_distribution_service().get_toc(tenant_id=_tenant_id(identity), work_id=work_id)
    return {
        'success': True,
        'code': 'OK',
        'message': 'toc retrieved',
        'data': data,
        'meta': {'total': len(data)},
        'trace_id': None,
    }


@router.get('/chapters/{chapter_id}')
async def get_client_chapter(chapter_id: str, identity: ApiKeyIdentity = Depends(get_api_key_identity)):
    _assert_capability(identity, 'read.chapter')
    data = build_content_distribution_service().read_chapter(tenant_id=_tenant_id(identity), chapter_id=chapter_id)
    return {
        'success': True,
        'code': 'OK',
        'message': 'chapter retrieved',
        'data': data['result'],
        'meta': {'route_summary': data['route_summary']},
        'trace_id': None,
    }
