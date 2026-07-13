from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.application.services.auth_service import AuthAppService
from app.core.permissions import Permission
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
    _=Depends(require_permission(Permission.USERS_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    users = await service.list_users()
    return {
        "success": True,
        "code": "OK",
        "message": "users listed",
        "data": users,
        "meta": {"total": len(users)},
        "trace_id": None,
    }


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
    return {"success": True, "code": "OK", "message": "user created", "data": user, "meta": {}, "trace_id": None}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.USERS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    user = await service.update_user_admin(user_id, identity.user_id, payload.display_name, payload.role)
    return {"success": True, "code": "OK", "message": "user updated", "data": user, "meta": {}, "trace_id": None}


@router.post("/users/{user_id}/enable")
async def enable_user(
    user_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.USERS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    user = await service.set_user_enabled_admin(user_id, True, identity.user_id)
    return {"success": True, "code": "OK", "message": "user enabled", "data": user, "meta": {}, "trace_id": None}


@router.post("/users/{user_id}/disable")
async def disable_user(
    user_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.USERS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    user = await service.set_user_enabled_admin(user_id, False, identity.user_id)
    return {"success": True, "code": "OK", "message": "user disabled", "data": user, "meta": {}, "trace_id": None}


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.USERS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.reset_password_admin(user_id, payload.password, identity.user_id)
    return {"success": True, "code": "OK", "message": "password reset", "data": {"user_id": user_id}, "meta": {}, "trace_id": None}


@router.get("/roles")
async def list_roles(
    _=Depends(require_permission(Permission.ROLES_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    roles = await service.list_roles()
    return {
        "success": True,
        "code": "OK",
        "message": "roles listed",
        "data": roles,
        "meta": {"total": len(roles)},
        "trace_id": None,
    }


@router.get("/permissions")
async def list_permissions(
    _=Depends(require_permission(Permission.PERMISSIONS_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    permissions = await service.list_permissions()
    return {
        "success": True,
        "code": "OK",
        "message": "permissions listed",
        "data": permissions,
        "meta": {"total": len(permissions)},
        "trace_id": None,
    }


@router.get("/api-keys")
async def list_api_keys(
    _=Depends(require_permission(Permission.API_KEYS_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    keys = await service.list_api_keys()
    return {
        "success": True,
        "code": "OK",
        "message": "api keys listed",
        "data": keys,
        "meta": {"total": len(keys)},
        "trace_id": None,
    }


@router.post("/api-keys")
async def create_api_key(
    payload: ApiKeyRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.API_KEYS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    key = await service.create_api_key(payload.name, payload.permissions, identity.user_id)
    return {
        "success": True,
        "code": "OK",
        "message": "api key created",
        "data": key,
        "meta": {},
        "trace_id": None,
    }


@router.patch("/api-keys/{api_key_id}/disable")
async def disable_api_key(
    api_key_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.API_KEYS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.set_api_key_enabled(api_key_id, False, identity.user_id)
    return {
        "success": True,
        "code": "OK",
        "message": "api key disabled",
        "data": {"api_key_id": api_key_id},
        "meta": {},
        "trace_id": None,
    }


@router.delete("/api-keys/{api_key_id}")
async def delete_api_key(
    api_key_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.API_KEYS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.delete_api_key(api_key_id, identity.user_id)
    return {
        "success": True,
        "code": "OK",
        "message": "api key deleted",
        "data": {"api_key_id": api_key_id},
        "meta": {},
        "trace_id": None,
    }


@router.get("/audit")
async def list_audit(
    _=Depends(require_permission(Permission.SYSTEM_AUDIT_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    items = await service.list_audit_events(limit=100)
    return {
        "success": True,
        "code": "OK",
        "message": "audit listed",
        "data": items,
        "meta": {"total": len(items)},
        "trace_id": None,
    }


@router.post("/sessions/{user_id}/revoke")
async def revoke_user_sessions(
    user_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.USERS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.revoke_user_sessions(user_id, identity.user_id)
    return {
        "success": True,
        "code": "OK",
        "message": "user sessions revoked",
        "data": {"user_id": user_id},
        "meta": {},
        "trace_id": None,
    }
