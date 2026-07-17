from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.core.response import ok
from app.infrastructure.persistence.factory import build_dashboard_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


@router.get("")
async def get_health(_=Depends(require_permission(Permission.HEALTH_CHECK))):
    service = build_dashboard_service()
    snapshot = await service.get_health()
    return ok(data=snapshot, message="health ready", meta={})
