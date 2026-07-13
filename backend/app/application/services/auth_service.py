from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.exceptions import AuthenticationException, NotFoundException, ValidationException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    generate_api_key,
    hash_api_key,
    hash_refresh_token,
    hash_password,
    verify_password,
)
from app.domain.entities.auth import ApiKey, AuditEvent, RefreshSession, User
from app.domain.repositories.auth_repo import AuthRepository


class AuthAppService:
    def __init__(self, repo: AuthRepository):
        self._repo = repo

    async def login(self, username: str, password: str) -> dict:
        user = await self._repo.get_user_by_username(username)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise AuthenticationException("Invalid username or password")

        permissions = await self._repo.get_permissions_for_user(user.id)
        await self._repo.update_user(user.id, last_login_at=datetime.now(timezone.utc))
        session_id = str(uuid4())
        refresh_token = create_refresh_token({"sub": str(user.id), "sid": session_id})
        await self._repo.save_refresh_session(
            RefreshSession(
                id=session_id,
                user_id=user.id,
                refresh_token_hash=hash_refresh_token(refresh_token),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
        )
        await self._repo.record_audit(
            AuditEvent(actor_id=user.id, action="auth.login", resource="session", detail=username)
        )
        access_token = create_access_token(
            {"sub": str(user.id), "permissions": permissions, "roles": user.role_names,
             "display_name": user.display_name, "sid": session_id}
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "permissions": permissions,
            "roles": user.role_names,
            "display_name": user.display_name,
        }

    async def refresh(self, raw_refresh_token: str) -> dict:
        payload = decode_refresh_token(raw_refresh_token)
        if not payload:
            raise AuthenticationException("Invalid refresh token")

        session = await self._repo.get_refresh_session(str(payload["sid"]))
        if session is None or session.revoked_at is not None:
            raise AuthenticationException("Refresh session is no longer valid")
        if session.refresh_token_hash != hash_refresh_token(raw_refresh_token):
            raise AuthenticationException("Refresh token mismatch")

        user = await self._repo.get_user_by_id(int(payload["sub"]))
        if user is None or not user.is_active:
            raise AuthenticationException("User account is disabled")
        permissions = await self._repo.get_permissions_for_user(user.id)
        access_token = create_access_token(
            {"sub": str(payload["sub"]), "permissions": permissions, "roles": user.role_names,
             "display_name": user.display_name, "sid": session.id}
        )
        await self._repo.record_audit(
            AuditEvent(
                actor_id=int(payload["sub"]),
                action="auth.refresh",
                resource="session",
                detail=session.id,
            )
        )
        return {"access_token": access_token, "token_type": "bearer"}

    async def logout(self, session_id: str, actor_id: int) -> None:
        if session_id:
            await self._repo.revoke_refresh_session(session_id)
        await self._repo.record_audit(
            AuditEvent(actor_id=actor_id, action="auth.logout", resource="session", detail=session_id)
        )

    async def logout_all(self, actor_id: int) -> None:
        await self._repo.revoke_all_refresh_sessions(actor_id)
        await self._repo.record_audit(
            AuditEvent(actor_id=actor_id, action="auth.logout_all", resource="session", detail=str(actor_id))
        )

    async def list_users(self) -> list[dict]:
        return [self._serialize_user(item) for item in await self._repo.list_users()]

    @staticmethod
    def _serialize_user(user: User) -> dict:
        role = "admin" if "admin" in user.role_names else (user.role_names[0] if user.role_names else "user")
        return {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": role,
            "roles": user.role_names,
            "status": "enabled" if user.is_active else "disabled",
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        }

    async def create_user_admin(self, username: str, display_name: str, role: str, password: str, actor_id: int) -> dict:
        if role not in {"admin", "user"}:
            raise ValidationException("Unsupported user role")
        if not username.strip() or len(password) < 8:
            raise ValidationException("Username is required and password must contain at least 8 characters")
        if await self._repo.get_user_by_username(username.strip()):
            raise ValidationException("Username already exists")
        user = await self._repo.save_user(User(
            username=username.strip(), display_name=display_name.strip(), password_hash=hash_password(password),
        ))
        await self._repo.assign_roles(user.id, [role])
        saved = await self._repo.get_user_by_id(user.id)
        await self._repo.record_audit(AuditEvent(actor_id=actor_id, action="user.create", resource="user", detail=str(user.id)))
        return self._serialize_user(saved)

    async def _assert_admin_change_allowed(self, target: User, actor_id: int, role: str | None = None, enabled: bool | None = None) -> None:
        if target.id == actor_id and enabled is False:
            raise ValidationException("You cannot disable your own account")
        removes_admin = "admin" in target.role_names and role == "user"
        disables_admin = "admin" in target.role_names and enabled is False
        if removes_admin or disables_admin:
            enabled_admins = [item for item in await self._repo.list_users() if item.is_active and "admin" in item.role_names]
            if len(enabled_admins) <= 1:
                raise ValidationException("Cannot disable or downgrade the last enabled administrator")

    async def update_user_admin(self, user_id: int, actor_id: int, display_name: str | None = None, role: str | None = None) -> dict:
        target = await self._repo.get_user_by_id(user_id)
        if target is None:
            raise NotFoundException("User not found")
        if role is not None and role not in {"admin", "user"}:
            raise ValidationException("Unsupported user role")
        await self._assert_admin_change_allowed(target, actor_id, role=role)
        updated = await self._repo.update_user(user_id, display_name=display_name, role_names=[role] if role else None)
        await self._repo.record_audit(AuditEvent(actor_id=actor_id, action="user.update", resource="user", detail=str(user_id)))
        return self._serialize_user(updated)

    async def set_user_enabled_admin(self, user_id: int, enabled: bool, actor_id: int) -> dict:
        target = await self._repo.get_user_by_id(user_id)
        if target is None:
            raise NotFoundException("User not found")
        await self._assert_admin_change_allowed(target, actor_id, enabled=enabled)
        updated = await self._repo.update_user(user_id, is_active=enabled)
        if not enabled:
            await self._repo.revoke_all_refresh_sessions(user_id)
        await self._repo.record_audit(AuditEvent(actor_id=actor_id, action="user.enable" if enabled else "user.disable", resource="user", detail=str(user_id)))
        return self._serialize_user(updated)

    async def reset_password_admin(self, user_id: int, password: str, actor_id: int) -> None:
        if len(password) < 8:
            raise ValidationException("Password must contain at least 8 characters")
        if await self._repo.get_user_by_id(user_id) is None:
            raise NotFoundException("User not found")
        await self._repo.update_user(user_id, password_hash=hash_password(password))
        await self._repo.revoke_all_refresh_sessions(user_id)
        await self._repo.record_audit(AuditEvent(actor_id=actor_id, action="user.password_reset", resource="user", detail=str(user_id)))

    async def list_roles(self) -> list[dict]:
        return [asdict(item) for item in await self._repo.list_roles()]

    async def list_permissions(self) -> list[str]:
        return await self._repo.list_permissions()

    async def list_api_keys(self) -> list[dict]:
        return [asdict(item) for item in await self._repo.list_api_keys()]

    async def create_api_key(self, name: str, permissions: list[str], actor_id: int) -> dict:
        raw_key = generate_api_key()
        saved = await self._repo.save_api_key(
            ApiKey(name=name, key_hash=hash_api_key(raw_key), permissions=permissions, is_enabled=True)
        )
        await self._repo.record_audit(
            AuditEvent(actor_id=actor_id, action="api_key.create", resource="api_key", detail=name)
        )
        payload = asdict(saved)
        payload["raw_key"] = raw_key
        return payload

    async def set_api_key_enabled(self, api_key_id: int, enabled: bool, actor_id: int) -> None:
        await self._repo.set_api_key_enabled(api_key_id, enabled)
        await self._repo.record_audit(
            AuditEvent(
                actor_id=actor_id,
                action="api_key.update",
                resource="api_key",
                detail=f"{api_key_id}:{enabled}",
            )
        )

    async def delete_api_key(self, api_key_id: int, actor_id: int) -> None:
        await self._repo.delete_api_key(api_key_id)
        await self._repo.record_audit(
            AuditEvent(actor_id=actor_id, action="api_key.delete", resource="api_key", detail=str(api_key_id))
        )

    async def list_audit_events(self, limit: int = 100) -> list[dict]:
        return [asdict(item) for item in await self._repo.list_audit_events(limit=limit)]

    async def revoke_user_sessions(self, target_user_id: int, actor_id: int) -> None:
        await self._repo.revoke_all_refresh_sessions(target_user_id)
        await self._repo.record_audit(
            AuditEvent(actor_id=actor_id, action="session.revoke", resource="session", detail=str(target_user_id))
        )
