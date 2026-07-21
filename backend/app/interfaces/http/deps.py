from fastapi import Depends, Header

from app.application.services.auth_service import AuthAppService
from app.core.exceptions import AuthenticationException, AuthorizationException
from app.core.permissions import Permission
from app.core.security import decode_access_token, hash_api_key
from app.domain.value_objects import OwnerScope
from app.infrastructure.persistence.factory import build_auth_repository


class RequestIdentity:
    def __init__(self, user_id: int, permissions: set[str], roles: set[str] | None = None, display_name: str = "", session_id: str | None = None):
        self.user_id = user_id
        self.permissions = permissions
        self.roles = roles or set()
        self.display_name = display_name
        self.session_id = session_id


class ApiKeyIdentity:
    def __init__(self, api_key_id: int, api_key_name: str, permissions: set[str]):
        self.api_key_id = api_key_id
        self.api_key_name = api_key_name
        self.permissions = permissions


def get_current_identity(authorization: str | None = Header(default=None)) -> RequestIdentity:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationException("Missing bearer token")
    payload = decode_access_token(authorization[7:])
    if not payload:
        raise AuthenticationException("Invalid access token")
    return RequestIdentity(
        user_id=int(payload["sub"]),
        permissions=set(payload.get("permissions", [])),
        roles=set(payload.get("roles", [])),
        display_name=str(payload.get("display_name", "")),
        session_id=payload.get("sid"),
    )


async def get_api_key_identity(authorization: str | None = Header(default=None)) -> ApiKeyIdentity:
    if not authorization or not authorization.startswith('Bearer lh_'):
        raise AuthenticationException('Missing API key')
    api_key = await build_auth_repository().get_api_key_by_hash(hash_api_key(authorization[7:]))
    if api_key is None or not api_key.is_enabled:
        raise AuthenticationException('Invalid API key')
    return ApiKeyIdentity(api_key.id, api_key.name, set(api_key.permissions))


async def get_current_principal(authorization: str | None = Header(default=None)) -> RequestIdentity | ApiKeyIdentity:
    """Authenticate either a user access token or a scoped application key."""
    if authorization and authorization.startswith("Bearer lh_"):
        return await get_api_key_identity(authorization)
    return get_current_identity(authorization)


def owner_scope_for(identity: RequestIdentity | ApiKeyIdentity) -> str:
    if isinstance(identity, RequestIdentity):
        return str(OwnerScope.user(identity.user_id))
    return str(OwnerScope.api_key(identity.api_key_id))


def require_principal_permission(permission: Permission):
    async def checker(identity: RequestIdentity | ApiKeyIdentity = Depends(get_current_principal)):
        if permission.value not in identity.permissions:
            raise AuthorizationException(f"Permission denied: {permission.value}")
        return identity

    return checker


def get_auth_service() -> AuthAppService:
    return AuthAppService(build_auth_repository())


def require_permission(permission: Permission):
    def checker(identity: RequestIdentity = Depends(get_current_identity)) -> RequestIdentity:
        if permission.value not in identity.permissions:
            raise AuthorizationException(f"Permission denied: {permission.value}")
        return identity

    return checker
