from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.entities.auth import ApiKey, AuditEvent, RefreshSession, Role, User


class AuthRepository(ABC):
    @abstractmethod
    async def get_user_by_username(self, username: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def save_user(self, user: User) -> User:
        raise NotImplementedError

    @abstractmethod
    async def list_users(self) -> list[User]:
        raise NotImplementedError

    @abstractmethod
    async def get_user_by_id(self, user_id: int) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def update_user(
        self,
        user_id: int,
        *,
        display_name: str | None = None,
        password_hash: str | None = None,
        is_active: bool | None = None,
        role_names: list[str] | None = None,
        last_login_at: datetime | None = None,
    ) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def ensure_role(self, name: str, permissions: list[str], description: str = "") -> Role:
        raise NotImplementedError

    @abstractmethod
    async def assign_roles(self, user_id: int, role_names: list[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_permissions_for_user(self, user_id: int) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def save_refresh_session(self, session: RefreshSession) -> RefreshSession:
        raise NotImplementedError

    @abstractmethod
    async def get_refresh_session(self, session_id: str) -> RefreshSession | None:
        raise NotImplementedError

    @abstractmethod
    async def revoke_refresh_session(self, session_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def revoke_all_refresh_sessions(self, user_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def save_api_key(self, api_key: ApiKey) -> ApiKey:
        raise NotImplementedError

    @abstractmethod
    async def get_api_key_by_hash(self, key_hash: str) -> ApiKey | None:
        raise NotImplementedError

    @abstractmethod
    async def list_api_keys(self) -> list[ApiKey]:
        raise NotImplementedError

    @abstractmethod
    async def list_enabled_api_keys(self) -> list[ApiKey]:
        """Return only API keys that can consume quota."""
        raise NotImplementedError

    @abstractmethod
    async def set_api_key_enabled(self, api_key_id: int, enabled: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_api_key(self, api_key_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_roles(self) -> list[Role]:
        raise NotImplementedError

    @abstractmethod
    async def list_permissions(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def record_audit(self, event: AuditEvent) -> AuditEvent:
        raise NotImplementedError

    @abstractmethod
    async def list_audit_events(self, limit: int = 100) -> list[AuditEvent]:
        raise NotImplementedError

    @abstractmethod
    async def delete_old_audit_events(self, days: int = 90) -> int:
        """Delete audit events older than ``days`` and return the count."""
        raise NotImplementedError
