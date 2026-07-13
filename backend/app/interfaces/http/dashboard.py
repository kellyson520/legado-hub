from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_dashboard_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


@router.get("")
async def get_dashboard(_=Depends(require_permission(Permission.DASHBOARD_READ))):
    service = build_dashboard_service()
    data = await service.get_dashboard()
    return {
        "success": True,
        "code": "OK",
        "message": "dashboard ready",
        "data": data,
        "meta": {},
        "trace_id": None,
    }


@router.get("/groups")
async def get_groups(_=Depends(require_permission(Permission.DASHBOARD_READ))):
    service = build_dashboard_service()
    groups = await service.get_groups()
    return {
        "success": True,
        "code": "OK",
        "message": "groups listed",
        "data": groups,
        "meta": {"total": len(groups)},
        "trace_id": None,
    }
