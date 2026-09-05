from fastapi import APIRouter, Depends

from app.core.response import ok
from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_source_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


@router.get("/book_sources")
async def export_book_sources(_=Depends(require_permission(Permission.EXPORT_READ))):
    service = build_source_service()
    result = await service.export_book_sources(enabled_only=False)
    return ok(data=result, message="export ready", meta={})
