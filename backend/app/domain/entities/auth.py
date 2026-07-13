from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Role:
    id: int = 0
    name: str = ""
    description: str = ""
    permissions: list[str] = field(default_factory=list)


@dataclass
class User:
    id: int = 0
    username: str = ""
    display_name: str = ""
    password_hash: str = ""
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: datetime | None = None
    role_names: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)


@dataclass
class RefreshSession:
    id: str = ""
    user_id: int = 0
    refresh_token_hash: str = ""
    expires_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass
class ApiKey:
    id: int = 0
    name: str = ""
    key_hash: str = ""
    permissions: list[str] = field(default_factory=list)
    is_enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AuditEvent:
    id: int = 0
    actor_id: int | None = None
    action: str = ""
    resource: str = ""
    detail: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
