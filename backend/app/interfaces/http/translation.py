from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, model_validator

from app.core.permissions import Permission
from app.core.response import from_paginated_result
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
async def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    status: str | None = Query(default=None, max_length=50),
    _=Depends(require_permission(Permission.TRANSLATION_RUN)),
):
    service = build_translation_service()
    result = await service.list_jobs_page(page=page, page_size=page_size, search=search, status=status)
    return from_paginated_result(result, message="translation jobs listed")


@router.post("/jobs")
async def create_job(payload: TranslationRequest, identity=Depends(require_permission(Permission.TRANSLATION_RUN))):
    service = build_translation_service()
    job = await service.create_job(payload.model_dump(), actor_id=str(identity.user_id))
    return {"success": True, "code": "OK", "message": "translation job queued", "data": job, "meta": {}, "trace_id": None}
