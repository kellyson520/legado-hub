from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.application.services.auth_service import AuthAppService
from app.core.permissions import Permission
from app.core.response import from_paginated_result, ok
from app.interfaces.http.deps import RequestIdentity, get_auth_service, get_current_identity, require_permission


router = APIRouter()


class ApiKeyRequest(BaseModel):
    name: str
    permissions: list[str]


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    display_name: str = Field(default="", max_length=100)
    role: str
    password: str = Field(min_length=8, max_length=256)


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    role: str | None = None


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=256)


@router.get("/users")
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    status: str | None = Query(default=None, max_length=20),
    _=Depends(require_permission(Permission.USERS_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    result = await service.list_users_page(page=page, page_size=page_size, search=search, status=status)
    return from_paginated_result(result, message="users listed")


@router.post("/users")
async def create_user(
    payload: CreateUserRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.USERS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    user = await service.create_user_admin(
        payload.username, payload.display_name, payload.role, payload.password, identity.user_id,
    )
    return ok(data=user, message="user created", meta={})


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.USERS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    user = await service.update_user_admin(user_id, identity.user_id, payload.display_name, payload.role)
    return ok(data=user, message="user updated", meta={})


@router.post("/users/{user_id}/enable")
async def enable_user(
    user_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.USERS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    user = await service.set_user_enabled_admin(user_id, True, identity.user_id)
    return ok(data=user, message="user enabled", meta={})


@router.post("/users/{user_id}/disable")
async def disable_user(
    user_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.USERS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    user = await service.set_user_enabled_admin(user_id, False, identity.user_id)
    return ok(data=user, message="user disabled", meta={})


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.USERS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.reset_password_admin(user_id, payload.password, identity.user_id)
    return ok(data={"user_id": user_id}, message="password reset", meta={})


@router.get("/roles")
async def list_roles(
    _=Depends(require_permission(Permission.ROLES_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    roles = await service.list_roles()
    return ok(data=roles, message="roles listed", meta={"total": len(roles)})


@router.get("/permissions")
async def list_permissions(
    _=Depends(require_permission(Permission.PERMISSIONS_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    permissions = await service.list_permissions()
    return ok(data=permissions, message="permissions listed", meta={"total": len(permissions)})


@router.get("/api-keys")
async def list_api_keys(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    status: str | None = Query(default=None, max_length=20),
    _=Depends(require_permission(Permission.API_KEYS_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    result = await service.list_api_keys_page(page=page, page_size=page_size, search=search, status=status)
    return from_paginated_result(result, message="api keys listed")


@router.post("/api-keys")
async def create_api_key(
    payload: ApiKeyRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.API_KEYS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    key = await service.create_api_key(payload.name, payload.permissions, identity.user_id)
    return ok(data=key, message="api key created", meta={})


@router.patch("/api-keys/{api_key_id}/disable")
async def disable_api_key(
    api_key_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.API_KEYS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.set_api_key_enabled(api_key_id, False, identity.user_id)
    return ok(data={"api_key_id": api_key_id}, message="api key disabled", meta={})


@router.delete("/api-keys/{api_key_id}")
async def delete_api_key(
    api_key_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.API_KEYS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.delete_api_key(api_key_id, identity.user_id)
    return ok(data={"api_key_id": api_key_id}, message="api key deleted", meta={})


@router.get("/audit")
async def list_audit(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    _=Depends(require_permission(Permission.SYSTEM_AUDIT_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    result = await service.list_audit_events_page(page=page, page_size=page_size, search=search)
    return from_paginated_result(result, message="audit listed")


@router.post("/sessions/{user_id}/revoke")
async def revoke_user_sessions(
    user_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.USERS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.revoke_user_sessions(user_id, identity.user_id)
    return ok(data={"user_id": user_id}, message="user sessions revoked", meta={})
