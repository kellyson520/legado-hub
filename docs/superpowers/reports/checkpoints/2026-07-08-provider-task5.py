from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_provider_platform_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


@router.get("/providers")
async def list_providers(_=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE))):
    service = build_provider_platform_service()
    data = service.list_provider_accounts()
    return {
        "success": True,
        "code": "OK",
        "message": "providers listed",
        "data": data,
        "meta": {"total": len(data)},
        "trace_id": None,
    }


@router.get("/quotas")
async def list_quota_policies(_=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE))):
    service = build_provider_platform_service()
    data = service.list_quota_policies()
    return {
        "success": True,
        "code": "OK",
        "message": "quota policies listed",
        "data": data,
        "meta": {"total": len(data)},
        "trace_id": None,
    }
