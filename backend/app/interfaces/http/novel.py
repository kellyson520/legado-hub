from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_novel_agent_service, build_novel_app_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


@router.get("/books")
async def list_books(_=Depends(require_permission(Permission.NOVEL_MANAGE))):
    service = build_novel_app_service()
    books = await service.list_books()
    return {"success": True, "code": "OK", "message": "novels listed", "data": books, "meta": {"total": len(books)}, "trace_id": None}


@router.post("/books/{novel_id}/analysis")
async def analyze_book(novel_id: str, identity=Depends(require_permission(Permission.NOVEL_MANAGE))):
    service = build_novel_agent_service()
    task = await service.start_analysis(novel_id, actor_id=str(identity.user_id))
    return {"success": True, "code": "OK", "message": "novel analysis queued", "data": task, "meta": {}, "trace_id": None}
