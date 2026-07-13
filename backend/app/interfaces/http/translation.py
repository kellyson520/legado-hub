from fastapi import APIRouter, Depends
from pydantic import BaseModel, model_validator

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_translation_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


class TranslationRequest(BaseModel):
    text: str = ""
    content_variant_id: str | None = None
    source_language: str
    target_language: str

    @model_validator(mode='after')
    def validate_source(self):
        if not self.text and not self.content_variant_id:
            raise ValueError('text or content_variant_id is required')
        return self


@router.get("/jobs")
async def list_jobs(_=Depends(require_permission(Permission.TRANSLATION_RUN))):
    service = build_translation_service()
    jobs = await service.list_jobs()
    return {"success": True, "code": "OK", "message": "translation jobs listed", "data": jobs, "meta": {"total": len(jobs)}, "trace_id": None}


@router.post("/jobs")
async def create_job(payload: TranslationRequest, identity=Depends(require_permission(Permission.TRANSLATION_RUN))):
    service = build_translation_service()
    job = await service.create_job(payload.model_dump(), actor_id=str(identity.user_id))
    return {"success": True, "code": "OK", "message": "translation job queued", "data": job, "meta": {}, "trace_id": None}
