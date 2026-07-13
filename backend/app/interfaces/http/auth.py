from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.application.services.auth_service import AuthAppService
from app.interfaces.http.deps import RequestIdentity, get_auth_service, get_current_identity


router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login")
async def login(payload: LoginRequest, service: AuthAppService = Depends(get_auth_service)):
    tokens = await service.login(payload.username, payload.password)
    return {
        "success": True,
        "code": "OK",
        "message": "login succeeded",
        "data": tokens,
        "meta": {},
        "trace_id": None,
    }


@router.post("/refresh")
async def refresh(payload: RefreshRequest, service: AuthAppService = Depends(get_auth_service)):
    tokens = await service.refresh(payload.refresh_token)
    return {
        "success": True,
        "code": "OK",
        "message": "token refreshed",
        "data": tokens,
        "meta": {},
        "trace_id": None,
    }


@router.post("/logout")
async def logout(
    identity: RequestIdentity = Depends(get_current_identity),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.logout(identity.session_id or "", identity.user_id)
    return {
        "success": True,
        "code": "OK",
        "message": "logout succeeded",
        "data": {"session_id": identity.session_id},
        "meta": {},
        "trace_id": None,
    }


@router.post("/logout-all")
async def logout_all(
    identity: RequestIdentity = Depends(get_current_identity),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.logout_all(identity.user_id)
    return {
        "success": True,
        "code": "OK",
        "message": "all sessions revoked",
        "data": {"user_id": identity.user_id},
        "meta": {},
        "trace_id": None,
    }


@router.get("/me")
async def me(identity: RequestIdentity = Depends(get_current_identity)):
    return {
        "success": True,
        "code": "OK",
        "message": "current identity",
        "data": {
            "user_id": identity.user_id,
            "roles": sorted(identity.roles),
            "display_name": identity.display_name,
            "permissions": sorted(identity.permissions),
            "session_id": identity.session_id,
        },
        "meta": {},
        "trace_id": None,
    }
