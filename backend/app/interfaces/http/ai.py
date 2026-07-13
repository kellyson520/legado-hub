from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_ai_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


class CharacterAnalysisRequest(BaseModel):
    title: str
    content: str


@router.get("/tasks")
async def list_ai_tasks(_=Depends(require_permission(Permission.AI_RUN))):
    service = build_ai_service()
    tasks = await service.list_tasks()
    return {"success": True, "code": "OK", "message": "ai tasks listed", "data": tasks, "meta": {"total": len(tasks)}, "trace_id": None}


@router.post("/tasks/character")
async def run_character_analysis(
    payload: CharacterAnalysisRequest,
    identity=Depends(require_permission(Permission.AI_RUN)),
):
    service = build_ai_service()
    task = await service.run_character_analysis(payload.model_dump(), actor_id=str(identity.user_id))
    return {"success": True, "code": "OK", "message": "ai character analysis queued", "data": task, "meta": {}, "trace_id": None}
