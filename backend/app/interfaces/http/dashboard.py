from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.core.response import ok
from app.infrastructure.persistence.factory import build_dashboard_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


@router.get("")
async def get_dashboard(_=Depends(require_permission(Permission.DASHBOARD_READ))):
    service = build_dashboard_service()
    data = await service.get_dashboard()
    return ok(data=data, message="dashboard ready", meta={})


@router.get("/groups")
async def get_groups(_=Depends(require_permission(Permission.DASHBOARD_READ))):
    service = build_dashboard_service()
    groups = await service.get_groups()
    return ok(data=groups, message="groups listed", meta={"total": len(groups)})
