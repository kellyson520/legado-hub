import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.permissions import Permission
from app.infrastructure.persistence.factory import (
    build_provider_platform_service,
    build_system_settings_service,
)
from app.interfaces.http.deps import require_permission


router = APIRouter()


class LLMSettingsRequest(BaseModel):
    provider_name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=2000)
    model: str = Field(min_length=1, max_length=120)


class SourceBuildAgentSettingsRequest(BaseModel):
    enabled: bool


class InteractiveBrowserSettingsRequest(BaseModel):
    enabled: bool
    automatic_enabled: bool = True
    max_sessions: int = Field(default=1, ge=1, le=3)
    session_timeout_seconds: int = Field(default=300, ge=60, le=600)


class ProviderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=2000)
    default_model: str = Field(default="", max_length=120)
    enabled: bool = True


class ProviderRouteEntryRequest(BaseModel):
    provider_account_id: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=120)
    enabled: bool = True


class ProviderRouteRequest(BaseModel):
    entries: list[ProviderRouteEntryRequest] = Field(min_length=1, max_length=20)


def _system_response(message: str, data):
    return {
        "success": True,
        "code": "OK",
        "message": message,
        "data": data,
        "meta": {},
        "trace_id": None,
    }


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


@router.post("/providers")
async def create_provider(
    payload: ProviderRequest,
    _=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE)),
):
    service = build_provider_platform_service()
    try:
        data = service.save_provider(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _system_response("provider saved", data)


@router.put("/providers/{provider_id}")
async def update_provider(
    provider_id: str,
    payload: ProviderRequest,
    _=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE)),
):
    service = build_provider_platform_service()
    try:
        data = service.save_provider(provider_id=provider_id, **payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _system_response("provider saved", data)


@router.post("/providers/{provider_id}/models")
async def discover_provider_models(
    provider_id: str,
    _=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE)),
):
    service = build_provider_platform_service()
    try:
        data = await service.discover_models(provider_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            detail = "Provider authentication failed; update the API key"
            status_code = 422
        else:
            detail = f"Provider model discovery failed (HTTP {exc.response.status_code})"
            status_code = 502
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Provider model discovery is unavailable") from exc
    return _system_response("provider models listed", data)


@router.get("/provider-routes/{provider_group}")
async def get_provider_route(
    provider_group: str,
    _=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE)),
):
    try:
        data = build_provider_platform_service().get_routes(provider_group)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _system_response("provider route loaded", data)


@router.put("/provider-routes/{provider_group}")
async def update_provider_route(
    provider_group: str,
    payload: ProviderRouteRequest,
    _=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE)),
):
    try:
        data = build_provider_platform_service().replace_routes(
            provider_group,
            [entry.model_dump() for entry in payload.entries],
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _system_response("provider route saved", data)


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


@router.get("/source-build-agent-settings")
async def get_source_build_agent_settings(
    _=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE)),
):
    data = build_system_settings_service().get_source_build_agent_settings()
    return {
        "success": True,
        "code": "OK",
        "message": "source build agent settings loaded",
        "data": data,
        "meta": {},
        "trace_id": None,
    }


@router.put("/source-build-agent-settings")
async def update_source_build_agent_settings(
    payload: SourceBuildAgentSettingsRequest,
    _=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE)),
):
    data = build_system_settings_service().set_source_build_agent_enabled(payload.enabled)
    return {
        "success": True,
        "code": "OK",
        "message": "source build agent settings saved",
        "data": data,
        "meta": {},
        "trace_id": None,
    }


@router.get('/interactive-browser-settings')
async def get_interactive_browser_settings(
    _=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE)),
):
    return _system_response(
        'interactive browser settings loaded',
        build_system_settings_service().get_interactive_browser_settings(),
    )


@router.put('/interactive-browser-settings')
async def update_interactive_browser_settings(
    payload: InteractiveBrowserSettingsRequest,
    _=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE)),
):
    return _system_response(
        'interactive browser settings saved',
        build_system_settings_service().set_interactive_browser_settings(**payload.model_dump()),
    )


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
