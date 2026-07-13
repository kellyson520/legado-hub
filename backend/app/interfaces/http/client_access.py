from fastapi import APIRouter, Depends

from app.interfaces.http.deps import ApiKeyIdentity, get_api_key_identity


router = APIRouter()


@router.get('/capabilities')
async def list_capabilities(identity: ApiKeyIdentity = Depends(get_api_key_identity)):
    return {
        'success': True,
        'code': 'OK',
        'message': 'client capabilities listed',
        'data': {
            'capabilities': sorted(identity.permissions),
            'principal': {'api_key_id': identity.api_key_id, 'api_key_name': identity.api_key_name},
        },
        'meta': {},
        'trace_id': None,
    }
