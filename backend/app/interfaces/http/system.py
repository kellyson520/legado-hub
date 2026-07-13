from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_provider_platform_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


class LLMSettingsRequest(BaseModel):
    provider_name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=2000)
    model: str = Field(min_length=1, max_length=120)


@router.get("/providers")
async def list_providers(_=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE))):
    service = build_provider_platform_service()
    data = service.list_provider_accounts()
    return {
        "success": True,
        "code": "OK",
        "message": "providers listed",
        "data": data,
        "meta": {"total": len(data)},
        "trace_id": None,
    }


@router.get("/llm-settings")
async def get_llm_settings(_=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE))):
    service = build_provider_platform_service()
    data = service.get_llm_settings(
        default_provider_name=settings.LLM_PROVIDER_NAME,
        default_model=settings.LLM_MODEL,
    )
    return {
        "success": True,
        "code": "OK",
        "message": "llm settings loaded",
        "data": data,
        "meta": {},
        "trace_id": None,
    }


@router.put("/llm-settings")
async def update_llm_settings(
    payload: LLMSettingsRequest,
    _=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE)),
):
    service = build_provider_platform_service()
    data = service.save_llm_settings(
        provider_name=payload.provider_name,
        base_url=payload.base_url,
        api_key=payload.api_key,
        model=payload.model,
    )
    return {
        "success": True,
        "code": "OK",
        "message": "llm settings saved",
        "data": data,
        "meta": {},
        "trace_id": None,
    }


@router.get("/quotas")
async def list_quota_policies(_=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE))):
    service = build_provider_platform_service()
    data = service.list_quota_policies()
    return {
        "success": True,
        "code": "OK",
        "message": "quota policies listed",
        "data": data,
        "meta": {"total": len(data)},
        "trace_id": None,
    }
