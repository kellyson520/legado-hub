from fastapi import APIRouter, Depends, Query

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_novel_agent_service, build_novel_app_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


@router.get("/books")
async def list_books(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    status: str | None = Query(default=None, max_length=50),
    _=Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    service = build_novel_app_service()
    result = await service.list_books_page(page=page, page_size=page_size, search=search, status=status)
    return {"success": True, "code": "OK", "message": "novels listed", "data": result["items"], "meta": result["meta"], "trace_id": None}


@router.post("/books/{novel_id}/analysis")
async def analyze_book(novel_id: str, identity=Depends(require_permission(Permission.NOVEL_MANAGE))):
    service = build_novel_agent_service()
    task = await service.start_analysis(novel_id, actor_id=str(identity.user_id))
    return {"success": True, "code": "OK", "message": "novel analysis queued", "data": task, "meta": {}, "trace_id": None}
