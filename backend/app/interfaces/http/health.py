from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_dashboard_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


@router.get("")
async def get_health(_=Depends(require_permission(Permission.HEALTH_CHECK))):
    service = build_dashboard_service()
    snapshot = await service.get_health()
    return {
        "success": True,
        "code": "OK",
        "message": "health ready",
        "data": snapshot,
        "meta": {},
        "trace_id": None,
    }
