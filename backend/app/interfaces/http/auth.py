from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.application.services.auth_service import AuthAppService
from app.core.response import ok
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
    return ok(data=tokens, message="login succeeded", meta={})


@router.post("/refresh")
async def refresh(payload: RefreshRequest, service: AuthAppService = Depends(get_auth_service)):
    tokens = await service.refresh(payload.refresh_token)
    return ok(data=tokens, message="token refreshed", meta={})


@router.post("/logout")
async def logout(
    identity: RequestIdentity = Depends(get_current_identity),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.logout(identity.session_id or "", identity.user_id)
    return ok(data={"session_id": identity.session_id}, message="logout succeeded", meta={})


@router.post("/logout-all")
async def logout_all(
    identity: RequestIdentity = Depends(get_current_identity),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.logout_all(identity.user_id)
    return ok(data={"user_id": identity.user_id}, message="all sessions revoked", meta={})


@router.get("/me")
async def me(identity: RequestIdentity = Depends(get_current_identity)):
    return ok(
        data={
            "user_id": identity.user_id,
            "roles": sorted(identity.roles),
            "display_name": identity.display_name,
            "permissions": sorted(identity.permissions),
            "session_id": identity.session_id,
        },
        message="current identity",
        meta={},
    )
