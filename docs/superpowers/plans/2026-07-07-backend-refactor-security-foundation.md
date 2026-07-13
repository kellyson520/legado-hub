# Backend Refactor Security Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current mixed v0/v1 backend runtime with a single authenticated main API, rebuilt SQLite schema, full RBAC, and a unified engine/source/platform foundation that runs locally on Python 3.13.

**Architecture:** Keep the existing `core / domain / application / infrastructure` layering, but establish a new runtime surface under `app/interfaces/http/` and rebuild the backend around validated settings, bcrypt + access/refresh auth, SQLite repository implementations, structured audit logs, and a normalized rule-engine pipeline. Old v0/v1 router trees remain only as migration reference and are removed from the runtime entrypoint.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, bcrypt/passlib, python-jose or PyJWT, SQLite, pytest, httpx, optional Redis with graceful degradation

---

> **Git note:** this working copy currently has no `.git`. Replace each “Commit” step with a filesystem checkpoint now; if the project is later placed under git, use the provided commit message verbatim.

## File Structure

```text
backend/app/
├── main.py                                      # single runtime entrypoint
├── database.py                                  # engine/session/base only
├── core/
│   ├── config.py                                # validated settings + env profiles
│   ├── security.py                              # bcrypt + access/refresh/api-key helpers
│   ├── permissions.py                           # permission constants + helpers
│   ├── response.py                              # unified success/error/meta helpers
│   ├── exceptions.py                            # structured app errors
│   ├── exception_handlers.py                    # FastAPI exception adapters
│   └── logging.py                               # trace-aware logging
├── domain/
│   ├── entities/
│   │   ├── auth.py                              # user/role/permission/session/api key
│   │   ├── source.py                            # source entities aligned to new API
│   │   └── engine.py                            # engine evaluation/repair/job models
│   └── repositories/
│       ├── auth_repo.py                         # auth + RBAC repository contract
│       ├── source_repo.py                       # source-facing contract
│       ├── engine_repo.py                       # engine repository contract
│       └── system_repo.py                       # audit/system/task contract
├── application/
│   └── services/
│       ├── auth_service.py                      # login/session/rbac/api-key use cases
│       ├── source_service.py                    # source/subscription/filter use cases
│       ├── dashboard_service.py                 # dashboard/export/health aggregates
│       ├── engine_service.py                    # generate/evaluate/repair/test harness
│       ├── translation_service.py               # re-homed under new auth/task model
│       ├── novel_app_service.py                 # re-homed under new auth/task model
│       └── novel_agent_service.py               # re-homed under new auth/task model
├── infrastructure/
│   ├── persistence/
│   │   ├── factory.py                           # repository wiring
│   │   └── sqlite/
│   │       ├── schema.py                        # SQLAlchemy models for new schema
│   │       ├── bootstrap.py                     # create tables + seed permissions
│   │       ├── auth_repo_impl.py                # SQLite auth/RBAC implementation
│   │       ├── source_repo_impl.py              # SQLite source implementation
│   │       ├── engine_repo_impl.py              # SQLite engine implementation
│   │       └── system_repo_impl.py              # audit/system implementation
│   └── legado/
│       └── engine/
│           ├── models.py                        # normalized rule result models
│           ├── parser.py                        # rule parsing + shorthand normalization
│           ├── executor.py                      # JSON/CSS/XPath/JS execution entrypoint
│           ├── validator.py                     # structural validation
│           ├── evaluator.py                     # score + diagnostics
│           ├── repairer.py                      # autofix + diff
│           ├── harness.py                       # online test harness
│           ├── generator.py                     # URL/sample driven generation adapter
│           ├── rule_selector.py                 # low-level selector retained but reduced
│           └── jsonpath_ext.py                  # JSONPath backend retained or wrapped
└── interfaces/
    └── http/
        ├── __init__.py
        ├── deps.py                              # auth/session/permission dependencies
        ├── router.py                            # aggregate router
        ├── auth.py                              # login/refresh/logout/me
        ├── admin.py                             # users/roles/permissions/api-keys/audit
        ├── sources.py                           # book/rss/subscriptions/filters
        ├── engine.py                            # generate/evaluate/repair/test
        ├── dashboard.py                         # aggregates
        ├── health.py                            # checks
        ├── export.py                            # authenticated export
        ├── ai.py                                # unified AI endpoints
        ├── translation.py                       # unified translation endpoints
        ├── novel.py                             # unified novel endpoints
        └── system.py                            # runtime/system endpoints

backend/tests/
├── test_runtime_bootstrap.py
├── test_core_security_main.py
├── test_rbac_permissions.py
├── test_auth_repo_sqlite.py
├── test_api_auth_main.py
├── test_api_admin_rbac.py
├── test_api_sources_main.py
├── test_api_dashboard_export.py
├── test_engine_pipeline.py
└── test_api_modules_main.py
```

---

### Task 1: Establish the single-runtime shell and validated local settings

**Files:**
- Create: `backend/app/interfaces/http/__init__.py`
- Create: `backend/app/interfaces/http/router.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/database.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_runtime_bootstrap.py`

- [ ] **Step 1: Write the failing runtime/config tests**

```python
# backend/tests/test_runtime_bootstrap.py
import os
from pathlib import Path

from fastapi.testclient import TestClient


def test_settings_default_to_project_local_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.setenv("APP_ENV", "test")

    from app.core.config import Settings

    settings = Settings(_env_file=None)
    assert settings.DB_PATH.endswith("backend/data/legado_hub.sqlite3")
    assert settings.SECRET_KEY
    assert settings.ENV in {"dev", "test", "prod"}


def test_root_no_longer_points_to_container_only_index(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.main import app

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["data"]["service"] == "LegadoHub API"


def test_status_is_the_only_public_baseline(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.main import app

    client = TestClient(app)
    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["success"] is True

    protected = client.get("/api/dashboard")
    assert protected.status_code in {401, 403, 404}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_runtime_bootstrap.py -v
```

Expected: fail because the current app still uses container root delivery, old settings defaults, and old router layout.

- [ ] **Step 3: Build the new runtime shell**

```python
# backend/app/core/config.py
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    ENV: str = Field(default="dev", alias="APP_ENV")
    APP_NAME: str = "LegadoHub API"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = False
    DB_PATH: str = str(Path(__file__).resolve().parents[2] / "data" / "legado_hub.sqlite3")
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    ALLOWED_ORIGINS: list[str] = ["http://127.0.0.1:3000", "http://localhost:3000"]


settings = Settings()
```

```python
# backend/app/database.py
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .core.config import settings

db_path = Path(settings.DB_PATH)
db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()
```

```python
# backend/app/interfaces/http/router.py
from fastapi import APIRouter

from . import auth, admin, sources, engine, dashboard, health, export, ai, translation, novel, system

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(engine.router, prefix="/engine", tags=["engine"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(translation.router, prefix="/translation", tags=["translation"])
api_router.include_router(novel.router, prefix="/novel", tags=["novel"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
```

```python
# backend/app/main.py
from fastapi import FastAPI

from .core.config import settings
from .core.exception_handlers import register_exception_handlers
from .interfaces.http.router import api_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)
register_exception_handlers(app)
app.include_router(api_router)


@app.get("/")
def root():
    return {
        "success": True,
        "code": "OK",
        "message": "service ready",
        "data": {"service": settings.APP_NAME, "version": settings.APP_VERSION},
        "trace_id": None,
    }


@app.get("/api/status")
def status():
    return {
        "success": True,
        "code": "OK",
        "message": "service ready",
        "data": {"service": settings.APP_NAME, "version": settings.APP_VERSION, "env": settings.ENV},
        "trace_id": None,
    }
```

- [ ] **Step 4: Run the runtime tests to verify they pass**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_runtime_bootstrap.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Checkpoint**

Current working copy checkpoint:

```powershell
Get-ChildItem backend\app\interfaces\http,backend\app\core,backend\app | Select-Object FullName
```

Future git commit message if repo is initialized later:

```text
feat: establish single runtime shell and validated local settings
```

---

### Task 2: Replace the security primitives with bcrypt, access/refresh tokens, and RBAC contracts

**Files:**
- Create: `backend/app/core/permissions.py`
- Create: `backend/app/domain/entities/auth.py`
- Create: `backend/app/domain/repositories/auth_repo.py`
- Modify: `backend/app/core/security.py`
- Modify: `backend/app/core/exceptions.py`
- Test: `backend/tests/test_core_security_main.py`
- Test: `backend/tests/test_rbac_permissions.py`

- [ ] **Step 1: Write failing security and RBAC tests**

```python
# backend/tests/test_core_security_main.py
def test_password_hash_is_not_plain_sha256(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.core.security import hash_password, verify_password

    hashed = hash_password("admin123456")
    assert hashed != "admin123456"
    assert hashed.startswith("$2")
    assert verify_password("admin123456", hashed) is True


def test_access_and_refresh_tokens_are_distinct(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.core.security import create_access_token, create_refresh_token

    access = create_access_token({"sub": "1", "username": "admin"})
    refresh = create_refresh_token({"sub": "1", "session_id": "abc"})
    assert access != refresh
    assert isinstance(access, str)
    assert isinstance(refresh, str)
```

```python
# backend/tests/test_rbac_permissions.py
from app.core.permissions import Permission, build_permission_matrix


def test_permission_constants_cover_core_and_extended_domains():
    values = {p.value for p in Permission}
    assert "users.read" in values
    assert "book_sources.write" in values
    assert "engine.generate" in values
    assert "translation.run" in values
    assert "novel.manage" in values
    assert "ai.run" in values


def test_permission_matrix_is_unique():
    matrix = build_permission_matrix()
    assert len(matrix) == len(set(matrix))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_core_security_main.py tests\test_rbac_permissions.py -v
```

Expected: fail because the current password hashing is SHA256-based and no full permission registry exists.

- [ ] **Step 3: Implement the new security primitives and RBAC contracts**

```python
# backend/app/core/permissions.py
from enum import Enum


DEFAULT_ROLE_NAME = "super_admin"


class Permission(str, Enum):
    USERS_READ = "users.read"
    USERS_WRITE = "users.write"
    ROLES_READ = "roles.read"
    ROLES_WRITE = "roles.write"
    PERMISSIONS_READ = "permissions.read"
    API_KEYS_READ = "api_keys.read"
    API_KEYS_WRITE = "api_keys.write"
    BOOK_SOURCES_READ = "book_sources.read"
    BOOK_SOURCES_WRITE = "book_sources.write"
    RSS_SOURCES_READ = "rss_sources.read"
    RSS_SOURCES_WRITE = "rss_sources.write"
    SUBSCRIPTIONS_READ = "subscriptions.read"
    SUBSCRIPTIONS_WRITE = "subscriptions.write"
    FILTER_RULES_READ = "filter_rules.read"
    FILTER_RULES_WRITE = "filter_rules.write"
    ENGINE_GENERATE = "engine.generate"
    ENGINE_EVALUATE = "engine.evaluate"
    ENGINE_REPAIR = "engine.repair"
    ENGINE_TEST = "engine.test"
    DASHBOARD_READ = "dashboard.read"
    HEALTH_CHECK = "health.check"
    EXPORT_READ = "export.read"
    SYSTEM_AUDIT_READ = "system.audit.read"
    SYSTEM_JOBS_MANAGE = "system.jobs.manage"
    AI_RUN = "ai.run"
    TRANSLATION_RUN = "translation.run"
    NOVEL_MANAGE = "novel.manage"


def build_permission_matrix() -> list[str]:
    return [permission.value for permission in Permission]
```

```python
# backend/app/domain/entities/auth.py
from dataclasses import dataclass, field
from datetime import datetime


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
    password_hash: str = ""
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
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
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AuditEvent:
    id: int = 0
    actor_id: int | None = None
    action: str = ""
    resource: str = ""
    detail: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
```

```python
# backend/app/domain/repositories/auth_repo.py
from abc import ABC, abstractmethod

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
    async def list_api_keys(self) -> list[ApiKey]:
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
```

```python
# backend/app/core/exceptions.py
class AppException(Exception):
    def __init__(self, code: str, message: str, status_code: int, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class AuthenticationException(AppException):
    def __init__(self, message: str = "authentication failed", details: dict | None = None):
        super().__init__("AUTHENTICATION_ERROR", message, 401, details)


class AuthorizationException(AppException):
    def __init__(self, message: str = "permission denied", details: dict | None = None):
        super().__init__("AUTHORIZATION_ERROR", message, 403, details)


class ValidationException(AppException):
    def __init__(self, message: str = "validation failed", details: dict | None = None):
        super().__init__("VALIDATION_ERROR", message, 422, details)


class NotFoundException(AppException):
    def __init__(self, message: str = "resource not found", details: dict | None = None):
        super().__init__("NOT_FOUND", message, 404, details)


class ConflictException(AppException):
    def __init__(self, message: str = "resource conflict", details: dict | None = None):
        super().__init__("CONFLICT", message, 409, details)
```

```python
# backend/app/core/security.py
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ACCESS_AUD = "access"
REFRESH_AUD = "refresh"
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(payload: dict) -> str:
    data = payload.copy()
    data["aud"] = ACCESS_AUD
    data["exp"] = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(data, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(payload: dict) -> str:
    data = payload.copy()
    data["aud"] = REFRESH_AUD
    data["jti"] = secrets.token_hex(16)
    data["exp"] = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(data, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, object]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM], audience=ACCESS_AUD)
    except JWTError:
        return {}


def decode_refresh_token(token: str) -> dict[str, object]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM], audience=REFRESH_AUD)
    except JWTError:
        return {}


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"lh_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run the new security/RBAC tests**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_core_security_main.py tests\test_rbac_permissions.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Checkpoint**

Future git commit message:

```text
feat: replace legacy security primitives with bcrypt and RBAC contracts
```

---

### Task 3: Rebuild the SQLite auth/RBAC schema and repository wiring

**Files:**
- Create: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Create: `backend/app/infrastructure/persistence/sqlite/bootstrap.py`
- Create: `backend/app/infrastructure/persistence/sqlite/auth_repo_impl.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Test: `backend/tests/test_auth_repo_sqlite.py`

- [ ] **Step 1: Write the failing SQLite auth repository tests**

```python
# backend/tests/test_auth_repo_sqlite.py
from pathlib import Path


async def test_auth_repo_can_create_admin_and_refresh_session(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "auth.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.domain.entities.auth import User, RefreshSession

    bootstrap_sqlite()
    repo = SQLiteAuthRepository()

    user = await repo.save_user(User(username="admin", password_hash="hash"))
    assert user.id > 0

    session = await repo.save_refresh_session(
        RefreshSession(id="sess-1", user_id=user.id, refresh_token_hash="abc")
    )
    assert session.id == "sess-1"
    assert (await repo.get_user_by_username("admin")).username == "admin"
```

- [ ] **Step 2: Run the repository test to verify it fails**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_auth_repo_sqlite.py -v
```

Expected: fail because no auth-specific SQLite schema/bootstrap/repository exists.

- [ ] **Step 3: Implement the schema, bootstrap, and repository wiring**

```python
# backend/app/infrastructure/persistence/sqlite/schema.py
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.database import Base


class UserModel(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RoleModel(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=False, default="")


class PermissionModel(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)


class UserRoleModel(Base):
    __tablename__ = "user_roles"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)


class RolePermissionModel(Base):
    __tablename__ = "role_permissions"
    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), primary_key=True)


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"
    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    refresh_token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class ApiKeyModel(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    key_hash = Column(String, nullable=False, unique=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ApiKeyPermissionModel(Base):
    __tablename__ = "api_key_permissions"
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), primary_key=True)
    permission_name = Column(String, primary_key=True)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False, index=True)
    resource = Column(String, nullable=False)
    detail = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
```

```python
# backend/app/infrastructure/persistence/sqlite/bootstrap.py
from app.core.permissions import DEFAULT_ROLE_NAME, build_permission_matrix
from app.database import Base, SessionLocal, engine

from .schema import PermissionModel
from .schema import RoleModel, RolePermissionModel


def bootstrap_sqlite() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = {row.name for row in db.query(PermissionModel).all()}
        for item in build_permission_matrix():
            if item not in existing:
                db.add(PermissionModel(name=item))
        role = db.query(RoleModel).filter(RoleModel.name == DEFAULT_ROLE_NAME).first()
        if role is None:
            role = RoleModel(name=DEFAULT_ROLE_NAME, description="Built-in full access role")
            db.add(role)
            db.flush()
        linked = {
            row.permission_id
            for row in db.query(RolePermissionModel).filter(RolePermissionModel.role_id == role.id).all()
        }
        permission_rows = db.query(PermissionModel).all()
        for row in permission_rows:
            if row.id not in linked:
                db.add(RolePermissionModel(role_id=role.id, permission_id=row.id))
        db.commit()
    finally:
        db.close()
```

```python
# backend/app/infrastructure/persistence/sqlite/auth_repo_impl.py
from app.database import SessionLocal
from app.domain.entities.auth import ApiKey, AuditEvent, RefreshSession, Role, User
from app.domain.repositories.auth_repo import AuthRepository

from .schema import (
    ApiKeyModel,
    ApiKeyPermissionModel,
    AuditLogModel,
    PermissionModel,
    RefreshTokenModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
    UserRoleModel,
)


class SQLiteAuthRepository(AuthRepository):
    def _role_names_for_user(self, db, user_id: int) -> list[str]:
        rows = (
            db.query(RoleModel.name)
            .join(UserRoleModel, UserRoleModel.role_id == RoleModel.id)
            .filter(UserRoleModel.user_id == user_id)
            .all()
        )
        return [row[0] for row in rows]

    def _permissions_for_user(self, db, user_id: int) -> list[str]:
        rows = (
            db.query(PermissionModel.name)
            .join(RolePermissionModel, RolePermissionModel.permission_id == PermissionModel.id)
            .join(RoleModel, RoleModel.id == RolePermissionModel.role_id)
            .join(UserRoleModel, UserRoleModel.role_id == RoleModel.id)
            .filter(UserRoleModel.user_id == user_id)
            .distinct()
            .all()
        )
        return [row[0] for row in rows]

    def _user_from_model(self, db, model: UserModel) -> User:
        return User(
            id=model.id,
            username=model.username,
            password_hash=model.password_hash,
            is_active=model.is_active,
            created_at=model.created_at,
            role_names=self._role_names_for_user(db, model.id),
            permissions=self._permissions_for_user(db, model.id),
        )

    async def save_user(self, user: User) -> User:
        db = SessionLocal()
        try:
            model = UserModel(username=user.username, password_hash=user.password_hash, is_active=user.is_active)
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._user_from_model(db, model)
        finally:
            db.close()

    async def get_user_by_username(self, username: str) -> User | None:
        db = SessionLocal()
        try:
            model = db.query(UserModel).filter(UserModel.username == username).first()
            return self._user_from_model(db, model) if model else None
        finally:
            db.close()

    async def list_users(self) -> list[User]:
        db = SessionLocal()
        try:
            rows = db.query(UserModel).order_by(UserModel.id.asc()).all()
            return [self._user_from_model(db, row) for row in rows]
        finally:
            db.close()

    async def ensure_role(self, name: str, permissions: list[str], description: str = "") -> Role:
        db = SessionLocal()
        try:
            role = db.query(RoleModel).filter(RoleModel.name == name).first()
            if role is None:
                role = RoleModel(name=name, description=description)
                db.add(role)
                db.flush()
            permission_rows = (
                db.query(PermissionModel).filter(PermissionModel.name.in_(permissions)).all()
                if permissions
                else []
            )
            db.query(RolePermissionModel).filter(RolePermissionModel.role_id == role.id).delete()
            for permission in permission_rows:
                db.add(RolePermissionModel(role_id=role.id, permission_id=permission.id))
            db.commit()
            return Role(
                id=role.id,
                name=role.name,
                description=role.description,
                permissions=[row.name for row in permission_rows],
            )
        finally:
            db.close()

    async def assign_roles(self, user_id: int, role_names: list[str]) -> None:
        db = SessionLocal()
        try:
            db.query(UserRoleModel).filter(UserRoleModel.user_id == user_id).delete()
            roles = db.query(RoleModel).filter(RoleModel.name.in_(role_names)).all()
            for role in roles:
                db.add(UserRoleModel(user_id=user_id, role_id=role.id))
            db.commit()
        finally:
            db.close()

    async def get_permissions_for_user(self, user_id: int) -> list[str]:
        db = SessionLocal()
        try:
            return self._permissions_for_user(db, user_id)
        finally:
            db.close()

    async def save_refresh_session(self, session: RefreshSession) -> RefreshSession:
        db = SessionLocal()
        try:
            model = RefreshTokenModel(
                id=session.id,
                user_id=session.user_id,
                refresh_token_hash=session.refresh_token_hash,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
            )
            db.add(model)
            db.commit()
            return session
        finally:
            db.close()

    async def get_refresh_session(self, session_id: str) -> RefreshSession | None:
        db = SessionLocal()
        try:
            model = db.query(RefreshTokenModel).filter(RefreshTokenModel.id == session_id).first()
            if model is None:
                return None
            return RefreshSession(
                id=model.id,
                user_id=model.user_id,
                refresh_token_hash=model.refresh_token_hash,
                expires_at=model.expires_at,
                revoked_at=model.revoked_at,
            )
        finally:
            db.close()

    async def revoke_refresh_session(self, session_id: str) -> None:
        from datetime import datetime

        db = SessionLocal()
        try:
            model = db.query(RefreshTokenModel).filter(RefreshTokenModel.id == session_id).first()
            if model is not None:
                model.revoked_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()

    async def revoke_all_refresh_sessions(self, user_id: int) -> None:
        from datetime import datetime

        db = SessionLocal()
        try:
            rows = db.query(RefreshTokenModel).filter(RefreshTokenModel.user_id == user_id).all()
            for row in rows:
                row.revoked_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    async def save_api_key(self, api_key: ApiKey) -> ApiKey:
        db = SessionLocal()
        try:
            model = ApiKeyModel(name=api_key.name, key_hash=api_key.key_hash, is_enabled=api_key.is_enabled)
            db.add(model)
            db.flush()
            for permission in api_key.permissions:
                db.add(ApiKeyPermissionModel(api_key_id=model.id, permission_name=permission))
            db.commit()
            db.refresh(model)
            api_key.id = model.id
            api_key.created_at = model.created_at
            return api_key
        finally:
            db.close()

    async def list_api_keys(self) -> list[ApiKey]:
        db = SessionLocal()
        try:
            items = []
            for model in db.query(ApiKeyModel).order_by(ApiKeyModel.id.asc()).all():
                permission_rows = (
                    db.query(ApiKeyPermissionModel.permission_name)
                    .filter(ApiKeyPermissionModel.api_key_id == model.id)
                    .all()
                )
                items.append(
                    ApiKey(
                        id=model.id,
                        name=model.name,
                        key_hash=model.key_hash,
                        is_enabled=model.is_enabled,
                        created_at=model.created_at,
                        permissions=[row[0] for row in permission_rows],
                    )
                )
            return items
        finally:
            db.close()

    async def set_api_key_enabled(self, api_key_id: int, enabled: bool) -> None:
        db = SessionLocal()
        try:
            model = db.query(ApiKeyModel).filter(ApiKeyModel.id == api_key_id).first()
            if model is not None:
                model.is_enabled = enabled
                db.commit()
        finally:
            db.close()

    async def delete_api_key(self, api_key_id: int) -> None:
        db = SessionLocal()
        try:
            db.query(ApiKeyPermissionModel).filter(ApiKeyPermissionModel.api_key_id == api_key_id).delete()
            db.query(ApiKeyModel).filter(ApiKeyModel.id == api_key_id).delete()
            db.commit()
        finally:
            db.close()

    async def list_roles(self) -> list[Role]:
        db = SessionLocal()
        try:
            roles = []
            for model in db.query(RoleModel).order_by(RoleModel.id.asc()).all():
                permission_rows = (
                    db.query(PermissionModel.name)
                    .join(RolePermissionModel, RolePermissionModel.permission_id == PermissionModel.id)
                    .filter(RolePermissionModel.role_id == model.id)
                    .all()
                )
                roles.append(
                    Role(
                        id=model.id,
                        name=model.name,
                        description=model.description,
                        permissions=[row[0] for row in permission_rows],
                    )
                )
            return roles
        finally:
            db.close()

    async def list_permissions(self) -> list[str]:
        db = SessionLocal()
        try:
            return [row.name for row in db.query(PermissionModel).order_by(PermissionModel.name.asc()).all()]
        finally:
            db.close()

    async def record_audit(self, event: AuditEvent) -> AuditEvent:
        db = SessionLocal()
        try:
            model = AuditLogModel(
                actor_id=event.actor_id,
                action=event.action,
                resource=event.resource,
                detail=event.detail,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            event.id = model.id
            event.created_at = model.created_at
            return event
        finally:
            db.close()

    async def list_audit_events(self, limit: int = 100) -> list[AuditEvent]:
        db = SessionLocal()
        try:
            rows = db.query(AuditLogModel).order_by(AuditLogModel.id.desc()).limit(limit).all()
            return [
                AuditEvent(
                    id=row.id,
                    actor_id=row.actor_id,
                    action=row.action,
                    resource=row.resource,
                    detail=row.detail,
                    created_at=row.created_at,
                )
                for row in rows
            ]
        finally:
            db.close()
```

```python
# backend/app/infrastructure/persistence/factory.py
from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository


def build_auth_repository() -> SQLiteAuthRepository:
    return SQLiteAuthRepository()
```

- [ ] **Step 4: Run the SQLite repository test**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_auth_repo_sqlite.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Checkpoint**

Future git commit message:

```text
feat: rebuild sqlite auth and rbac schema
```

---

### Task 4: Add authenticated auth/admin APIs with access-refresh session flow and permission guards

**Files:**
- Create: `backend/app/interfaces/http/deps.py`
- Create: `backend/app/interfaces/http/auth.py`
- Create: `backend/app/interfaces/http/admin.py`
- Modify: `backend/app/application/services/auth_service.py`
- Test: `backend/tests/test_api_auth_main.py`
- Test: `backend/tests/test_api_admin_rbac.py`

- [ ] **Step 1: Write the failing API tests**

```python
# backend/tests/test_api_auth_main.py
import asyncio

from fastapi.testclient import TestClient

def test_login_refresh_logout_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "auth-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.core.permissions import DEFAULT_ROLE_NAME
    from app.core.security import hash_password
    from app.domain.entities.auth import User
    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = SQLiteAuthRepository()
    user = asyncio.run(repo.save_user(User(username="admin", password_hash=hash_password("admin123456"))))
    asyncio.run(repo.assign_roles(user.id, [DEFAULT_ROLE_NAME]))

    from app.main import app

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})
    assert login.status_code == 200
    payload = login.json()["data"]
    assert payload["access_token"]
    assert payload["refresh_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert me.status_code == 200
    assert me.json()["data"]["user_id"] > 0

    refresh = client.post("/api/auth/refresh", json={"refresh_token": payload["refresh_token"]})
    assert refresh.status_code == 200
    assert refresh.json()["data"]["access_token"]

    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert logout.status_code == 200
```

```python
# backend/tests/test_api_admin_rbac.py
from fastapi.testclient import TestClient

def test_admin_route_requires_permission(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    denied = create_access_token({"sub": "1", "permissions": ["dashboard.read"], "sid": "s-1"})
    denied_response = client.get("/api/admin/users", headers={"Authorization": f"Bearer {denied}"})
    assert denied_response.status_code == 403

    allowed = create_access_token({"sub": "1", "permissions": ["users.read"], "sid": "s-2"})
    allowed_response = client.get("/api/admin/users", headers={"Authorization": f"Bearer {allowed}"})
    assert allowed_response.status_code == 200
```

- [ ] **Step 2: Run the tests to confirm failure**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_api_auth_main.py tests\test_api_admin_rbac.py -v
```

Expected: fail because the new auth/admin routes and deps do not exist yet.

- [ ] **Step 3: Implement auth dependencies and API surface**

```python
# backend/app/interfaces/http/deps.py
from fastapi import Depends, Header

from app.application.services.auth_service import AuthAppService
from app.core.exceptions import AuthenticationException, AuthorizationException
from app.core.permissions import Permission
from app.core.security import decode_access_token
from app.infrastructure.persistence.factory import build_auth_repository


class RequestIdentity:
    def __init__(self, user_id: int, permissions: set[str], session_id: str | None = None):
        self.user_id = user_id
        self.permissions = permissions
        self.session_id = session_id


def get_current_identity(authorization: str | None = Header(default=None)) -> RequestIdentity:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationException("Missing bearer token")
    payload = decode_access_token(authorization[7:])
    if not payload:
        raise AuthenticationException("Invalid access token")
    return RequestIdentity(
        user_id=int(payload["sub"]),
        permissions=set(payload.get("permissions", [])),
        session_id=payload.get("sid"),
    )


def get_auth_service() -> AuthAppService:
    return AuthAppService(build_auth_repository())


def require_permission(permission: Permission):
    def checker(identity: RequestIdentity = Depends(get_current_identity)) -> RequestIdentity:
        if permission.value not in identity.permissions:
            raise AuthorizationException(f"Permission denied: {permission.value}")
        return identity
    return checker
```

```python
# backend/app/application/services/auth_service.py
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.exceptions import AuthenticationException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    generate_api_key,
    hash_api_key,
    hash_refresh_token,
    verify_password,
)
from app.domain.entities.auth import ApiKey, AuditEvent, RefreshSession
from app.domain.repositories.auth_repo import AuthRepository


class AuthAppService:
    def __init__(self, repo: AuthRepository):
        self._repo = repo

    async def login(self, username: str, password: str) -> dict:
        user = await self._repo.get_user_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthenticationException("Invalid username or password")
        permissions = await self._repo.get_permissions_for_user(user.id)
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
            {"sub": str(user.id), "permissions": permissions, "sid": session_id}
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "permissions": permissions,
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
        permissions = await self._repo.get_permissions_for_user(int(payload["sub"]))
        access_token = create_access_token(
            {"sub": str(payload["sub"]), "permissions": permissions, "sid": session.id}
        )
        await self._repo.record_audit(
            AuditEvent(actor_id=int(payload["sub"]), action="auth.refresh", resource="session", detail=session.id)
        )
        return {"access_token": access_token, "token_type": "bearer"}

    async def logout(self, session_id: str, actor_id: int) -> None:
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
        return [asdict(item) for item in await self._repo.list_users()]

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
            AuditEvent(actor_id=actor_id, action="api_key.update", resource="api_key", detail=f"{api_key_id}:{enabled}")
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
```

```python
# backend/app/interfaces/http/auth.py
from pydantic import BaseModel
from fastapi import APIRouter, Depends

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
    return {"success": True, "code": "OK", "message": "login succeeded", "data": tokens, "meta": {}, "trace_id": None}


@router.post("/refresh")
async def refresh(payload: RefreshRequest, service: AuthAppService = Depends(get_auth_service)):
    tokens = await service.refresh(payload.refresh_token)
    return {"success": True, "code": "OK", "message": "token refreshed", "data": tokens, "meta": {}, "trace_id": None}


@router.post("/logout")
async def logout(
    identity: RequestIdentity = Depends(get_current_identity),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.logout(identity.session_id or "", identity.user_id)
    return {"success": True, "code": "OK", "message": "logout succeeded", "data": {"session_id": identity.session_id}, "meta": {}, "trace_id": None}


@router.post("/logout-all")
async def logout_all(
    identity: RequestIdentity = Depends(get_current_identity),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.logout_all(identity.user_id)
    return {"success": True, "code": "OK", "message": "all sessions revoked", "data": {"user_id": identity.user_id}, "meta": {}, "trace_id": None}


@router.get("/me")
async def me(identity: RequestIdentity = Depends(get_current_identity)):
    return {
        "success": True,
        "code": "OK",
        "message": "current identity",
        "data": {"user_id": identity.user_id, "permissions": sorted(identity.permissions), "session_id": identity.session_id},
        "meta": {},
        "trace_id": None,
    }
```

```python
# backend/app/interfaces/http/admin.py
from pydantic import BaseModel
from fastapi import APIRouter, Depends

from app.application.services.auth_service import AuthAppService
from app.core.permissions import Permission
from app.interfaces.http.deps import RequestIdentity, get_auth_service, get_current_identity, require_permission

router = APIRouter()


class ApiKeyRequest(BaseModel):
    name: str
    permissions: list[str]


@router.get("/users")
async def list_users(
    _=Depends(require_permission(Permission.USERS_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    users = await service.list_users()
    return {"success": True, "code": "OK", "message": "users listed", "data": users, "meta": {"total": len(users)}, "trace_id": None}


@router.get("/roles")
async def list_roles(
    _=Depends(require_permission(Permission.ROLES_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    roles = await service.list_roles()
    return {"success": True, "code": "OK", "message": "roles listed", "data": roles, "meta": {"total": len(roles)}, "trace_id": None}


@router.get("/permissions")
async def list_permissions(
    _=Depends(require_permission(Permission.PERMISSIONS_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    permissions = await service.list_permissions()
    return {"success": True, "code": "OK", "message": "permissions listed", "data": permissions, "meta": {"total": len(permissions)}, "trace_id": None}


@router.get("/api-keys")
async def list_api_keys(
    _=Depends(require_permission(Permission.API_KEYS_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    keys = await service.list_api_keys()
    return {"success": True, "code": "OK", "message": "api keys listed", "data": keys, "meta": {"total": len(keys)}, "trace_id": None}


@router.post("/api-keys")
async def create_api_key(
    payload: ApiKeyRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.API_KEYS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    item = await service.create_api_key(payload.name, payload.permissions, identity.user_id)
    return {"success": True, "code": "OK", "message": "api key created", "data": item, "meta": {}, "trace_id": None}


@router.patch("/api-keys/{api_key_id}/disable")
async def disable_api_key(
    api_key_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.API_KEYS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.set_api_key_enabled(api_key_id, False, identity.user_id)
    return {"success": True, "code": "OK", "message": "api key disabled", "data": {"api_key_id": api_key_id}, "meta": {}, "trace_id": None}


@router.delete("/api-keys/{api_key_id}")
async def delete_api_key(
    api_key_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.API_KEYS_WRITE)),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.delete_api_key(api_key_id, identity.user_id)
    return {"success": True, "code": "OK", "message": "api key deleted", "data": {"api_key_id": api_key_id}, "meta": {}, "trace_id": None}


@router.get("/audit")
async def list_audit(
    _=Depends(require_permission(Permission.SYSTEM_AUDIT_READ)),
    service: AuthAppService = Depends(get_auth_service),
):
    items = await service.list_audit_events(limit=100)
    return {"success": True, "code": "OK", "message": "audit listed", "data": items, "meta": {"total": len(items)}, "trace_id": None}


@router.post("/sessions/{user_id}/revoke")
async def revoke_user_sessions(
    user_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.SYSTEM_JOBS_MANAGE)),
    service: AuthAppService = Depends(get_auth_service),
):
    await service.revoke_user_sessions(user_id, identity.user_id)
    return {"success": True, "code": "OK", "message": "user sessions revoked", "data": {"user_id": user_id}, "meta": {}, "trace_id": None}
```

- [ ] **Step 4: Run the auth/admin API tests**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_api_auth_main.py tests\test_api_admin_rbac.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Checkpoint**

Future git commit message:

```text
feat: add authenticated auth and admin api surface
```

---

### Task 5: Rewrite source, export, dashboard, and health flows on the new contracts

**Files:**
- Modify: `backend/app/domain/repositories/source_repo.py`
- Modify: `backend/app/application/services/source_service.py`
- Create: `backend/app/application/services/dashboard_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/bootstrap.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/source_repo_impl.py`
- Create: `backend/app/interfaces/http/sources.py`
- Create: `backend/app/interfaces/http/dashboard.py`
- Create: `backend/app/interfaces/http/export.py`
- Create: `backend/app/interfaces/http/health.py`
- Test: `backend/tests/test_api_sources_main.py`
- Test: `backend/tests/test_api_dashboard_export.py`

- [ ] **Step 1: Write the failing source/dashboard/export tests**

```python
# backend/tests/test_api_sources_main.py
from fastapi.testclient import TestClient

def test_sources_are_protected_and_paginated_in_meta(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    unauth = client.get("/api/sources/book_sources")
    assert unauth.status_code == 401

    token = create_access_token({"sub": "1", "permissions": ["book_sources.read"], "sid": "sources-1"})
    auth = client.get(
        "/api/sources/book_sources?page=1&page_size=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert auth.status_code == 200
    assert auth.json()["meta"] == {"page": 1, "page_size": 20, "total": 0, "total_pages": 0}
```

```python
# backend/tests/test_api_dashboard_export.py
from fastapi.testclient import TestClient

def test_export_requires_auth(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    assert client.get("/api/export/book_sources").status_code == 401

    token = create_access_token(
        {"sub": "1", "permissions": ["dashboard.read", "export.read", "health.check"], "sid": "dash-1"}
    )
    dashboard = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert dashboard.status_code == 200
    assert {"book_sources", "rss_sources", "subscriptions", "filter_rules"} <= set(
        dashboard.json()["data"].keys()
    )

    export = client.get("/api/export/book_sources", headers={"Authorization": f"Bearer {token}"})
    assert export.status_code == 200
    assert isinstance(export.json()["data"]["items"], list)
```

- [ ] **Step 2: Run the tests to confirm failure**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_api_sources_main.py tests\test_api_dashboard_export.py -v
```

Expected: fail because the new source/export/dashboard/health routes do not exist yet.

- [ ] **Step 3: Implement the source-facing contracts**

```python
# backend/app/domain/repositories/source_repo.py
from abc import ABC, abstractmethod


class SourceRepository(ABC):
    @abstractmethod
    async def list_book_sources(
        self, page: int, page_size: int, enabled_only: bool = False
    ) -> tuple[list[dict], int]:
        raise NotImplementedError

    @abstractmethod
    async def create_book_source(self, data: dict, actor_id: int) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def update_book_source(self, source_id: int, data: dict, actor_id: int) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def delete_book_source(self, source_id: int, actor_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_groups(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    async def export_book_sources(self, enabled_only: bool = False) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    async def health_snapshot(self) -> dict:
        raise NotImplementedError
```

```python
# backend/app/infrastructure/persistence/sqlite/schema.py
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database import Base


class BookSourceModel(Base):
    __tablename__ = "book_sources"
    id = Column(Integer, primary_key=True, autoincrement=True)
    bookSourceName = Column(String, nullable=False)
    bookSourceUrl = Column(String, nullable=False, unique=True, index=True)
    bookSourceGroup = Column(String, nullable=False, default="default")
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RssSourceModel(Base):
    __tablename__ = "rss_sources"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sourceName = Column(String, nullable=False)
    sourceUrl = Column(String, nullable=False, unique=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True)


class SubscriptionModel(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)


class FilterRuleModel(Base):
    __tablename__ = "filter_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    pattern = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
```

```python
# backend/app/infrastructure/persistence/sqlite/bootstrap.py
from app.database import Base, SessionLocal, engine

from . import schema as _schema
from .schema import PermissionModel, RoleModel, RolePermissionModel
from app.core.permissions import DEFAULT_ROLE_NAME, build_permission_matrix


def bootstrap_sqlite() -> None:
    _ = _schema
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = {row.name for row in db.query(PermissionModel).all()}
        for item in build_permission_matrix():
            if item not in existing:
                db.add(PermissionModel(name=item))
        role = db.query(RoleModel).filter(RoleModel.name == DEFAULT_ROLE_NAME).first()
        if role is None:
            role = RoleModel(name=DEFAULT_ROLE_NAME, description="Built-in full access role")
            db.add(role)
            db.flush()
        linked = {
            row.permission_id
            for row in db.query(RolePermissionModel).filter(RolePermissionModel.role_id == role.id).all()
        }
        for row in db.query(PermissionModel).all():
            if row.id not in linked:
                db.add(RolePermissionModel(role_id=role.id, permission_id=row.id))
        db.commit()
    finally:
        db.close()
```

```python
# backend/app/application/services/source_service.py
from math import ceil

from app.domain.repositories.source_repo import SourceRepository


class SourceAppService:
    def __init__(self, repo: SourceRepository):
        self._repo = repo

    async def list_book_sources(self, page: int, page_size: int, enabled_only: bool = False) -> dict:
        items, total = await self._repo.list_book_sources(page=page, page_size=page_size, enabled_only=enabled_only)
        total_pages = ceil(total / page_size) if total else 0
        return {
            "items": items,
            "meta": {"page": page, "page_size": page_size, "total": total, "total_pages": total_pages},
        }

    async def create_book_source(self, payload: dict, actor_id: int) -> dict:
        return await self._repo.create_book_source(payload, actor_id)

    async def update_book_source(self, source_id: int, payload: dict, actor_id: int) -> dict:
        return await self._repo.update_book_source(source_id, payload, actor_id)

    async def delete_book_source(self, source_id: int, actor_id: int) -> None:
        await self._repo.delete_book_source(source_id, actor_id)

    async def export_book_sources(self, enabled_only: bool = False) -> dict:
        items = await self._repo.export_book_sources(enabled_only=enabled_only)
        return {"items": items, "count": len(items)}
```

```python
# backend/app/application/services/dashboard_service.py
from app.domain.repositories.source_repo import SourceRepository


class DashboardService:
    def __init__(self, repo: SourceRepository):
        self._repo = repo

    async def get_dashboard(self) -> dict:
        snapshot = await self._repo.health_snapshot()
        return {
            "book_sources": snapshot["book_sources_total"],
            "rss_sources": snapshot["rss_sources_total"],
            "subscriptions": snapshot["subscriptions_total"],
            "filter_rules": snapshot["filter_rules_total"],
        }

    async def get_groups(self) -> list[dict]:
        return await self._repo.list_groups()

    async def get_health(self) -> dict:
        return await self._repo.health_snapshot()
```

```python
# backend/app/infrastructure/persistence/factory.py
from app.application.services.dashboard_service import DashboardService
from app.application.services.source_service import SourceAppService
from app.infrastructure.persistence.sqlite.source_repo_impl import SQLiteSourceRepository


def build_source_repository() -> SQLiteSourceRepository:
    return SQLiteSourceRepository()


def build_source_service() -> SourceAppService:
    return SourceAppService(build_source_repository())


def build_dashboard_service() -> DashboardService:
    return DashboardService(build_source_repository())
```

```python
# backend/app/infrastructure/persistence/sqlite/source_repo_impl.py
from sqlalchemy import func

from app.database import SessionLocal
from app.domain.repositories.source_repo import SourceRepository

from .schema import BookSourceModel, FilterRuleModel, RssSourceModel, SubscriptionModel


class SQLiteSourceRepository(SourceRepository):
    def _book_to_dict(self, model: BookSourceModel) -> dict:
        return {
            "id": model.id,
            "bookSourceName": model.bookSourceName,
            "bookSourceUrl": model.bookSourceUrl,
            "bookSourceGroup": model.bookSourceGroup,
            "enabled": model.enabled,
        }

    async def list_book_sources(
        self, page: int, page_size: int, enabled_only: bool = False
    ) -> tuple[list[dict], int]:
        db = SessionLocal()
        try:
            query = db.query(BookSourceModel).order_by(BookSourceModel.id.asc())
            if enabled_only:
                query = query.filter(BookSourceModel.enabled == True)
            total = query.count()
            rows = query.offset((page - 1) * page_size).limit(page_size).all()
            return [self._book_to_dict(row) for row in rows], total
        finally:
            db.close()

    async def create_book_source(self, data: dict, actor_id: int) -> dict:
        db = SessionLocal()
        try:
            model = BookSourceModel(**data)
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._book_to_dict(model) | {"created_by": actor_id}
        finally:
            db.close()

    async def update_book_source(self, source_id: int, data: dict, actor_id: int) -> dict:
        db = SessionLocal()
        try:
            model = db.query(BookSourceModel).filter(BookSourceModel.id == source_id).first()
            for key, value in data.items():
                setattr(model, key, value)
            db.commit()
            db.refresh(model)
            return self._book_to_dict(model) | {"updated_by": actor_id}
        finally:
            db.close()

    async def delete_book_source(self, source_id: int, actor_id: int) -> None:
        db = SessionLocal()
        try:
            db.query(BookSourceModel).filter(BookSourceModel.id == source_id).delete()
            db.commit()
        finally:
            db.close()

    async def list_groups(self) -> list[dict]:
        db = SessionLocal()
        try:
            rows = (
                db.query(BookSourceModel.bookSourceGroup, func.count(BookSourceModel.id))
                .group_by(BookSourceModel.bookSourceGroup)
                .order_by(BookSourceModel.bookSourceGroup.asc())
                .all()
            )
            return [{"name": row[0] or "default", "count": row[1]} for row in rows]
        finally:
            db.close()

    async def export_book_sources(self, enabled_only: bool = False) -> list[dict]:
        items, _ = await self.list_book_sources(page=1, page_size=10000, enabled_only=enabled_only)
        return items

    async def health_snapshot(self) -> dict:
        db = SessionLocal()
        try:
            return {
                "book_sources_total": db.query(BookSourceModel).count(),
                "book_sources_enabled": db.query(BookSourceModel).filter(BookSourceModel.enabled == True).count(),
                "rss_sources_total": db.query(RssSourceModel).count(),
                "subscriptions_total": db.query(SubscriptionModel).count(),
                "filter_rules_total": db.query(FilterRuleModel).count(),
            }
        finally:
            db.close()
```

```python
# backend/app/interfaces/http/sources.py
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_source_service
from app.interfaces.http.deps import RequestIdentity, get_current_identity, require_permission

router = APIRouter()


class BookSourcePayload(BaseModel):
    bookSourceName: str
    bookSourceUrl: str
    enabled: bool = True


@router.get("/book_sources")
async def list_book_sources(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    enabled_only: bool = False,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_service()
    result = await service.list_book_sources(page=page, page_size=page_size, enabled_only=enabled_only)
    return {"success": True, "code": "OK", "message": "book sources listed", "data": result["items"], "meta": result["meta"], "trace_id": None}


@router.post("/book_sources")
async def create_book_source(
    payload: BookSourcePayload,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    service = build_source_service()
    item = await service.create_book_source(payload.model_dump(), identity.user_id)
    return {"success": True, "code": "OK", "message": "book source created", "data": item, "meta": {}, "trace_id": None}


@router.put("/book_sources/{source_id}")
async def update_book_source(
    source_id: int,
    payload: BookSourcePayload,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    service = build_source_service()
    item = await service.update_book_source(source_id, payload.model_dump(), identity.user_id)
    return {"success": True, "code": "OK", "message": "book source updated", "data": item, "meta": {}, "trace_id": None}


@router.delete("/book_sources/{source_id}")
async def delete_book_source(
    source_id: int,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    service = build_source_service()
    await service.delete_book_source(source_id, identity.user_id)
    return {"success": True, "code": "OK", "message": "book source deleted", "data": {"source_id": source_id}, "meta": {}, "trace_id": None}
```

```python
# backend/app/interfaces/http/dashboard.py
from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_dashboard_service
from app.interfaces.http.deps import require_permission

router = APIRouter()


@router.get("")
async def get_dashboard(_=Depends(require_permission(Permission.DASHBOARD_READ))):
    service = build_dashboard_service()
    data = await service.get_dashboard()
    return {"success": True, "code": "OK", "message": "dashboard ready", "data": data, "meta": {}, "trace_id": None}


@router.get("/groups")
async def get_groups(_=Depends(require_permission(Permission.DASHBOARD_READ))):
    service = build_dashboard_service()
    groups = await service.get_groups()
    return {"success": True, "code": "OK", "message": "groups listed", "data": groups, "meta": {"total": len(groups)}, "trace_id": None}
```

```python
# backend/app/interfaces/http/export.py
from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_source_service
from app.interfaces.http.deps import require_permission

router = APIRouter()


@router.get("/book_sources")
async def export_book_sources(_=Depends(require_permission(Permission.EXPORT_READ))):
    service = build_source_service()
    result = await service.export_book_sources(enabled_only=False)
    return {"success": True, "code": "OK", "message": "export ready", "data": result, "meta": {}, "trace_id": None}
```

```python
# backend/app/interfaces/http/health.py
from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_dashboard_service
from app.interfaces.http.deps import require_permission

router = APIRouter()


@router.get("")
async def get_health(_=Depends(require_permission(Permission.HEALTH_CHECK))):
    service = build_dashboard_service()
    snapshot = await service.get_health()
    return {"success": True, "code": "OK", "message": "health ready", "data": snapshot, "meta": {}, "trace_id": None}
```

- [ ] **Step 4: Run the source/dashboard/export tests**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_api_sources_main.py tests\test_api_dashboard_export.py -v
```

Expected: 2 passed, proving pagination is emitted via `meta`, dashboard counts come from repository aggregates, and export remains authenticated.

- [ ] **Step 5: Checkpoint**

Future git commit message:

```text
feat: rewrite source dashboard export and health flows on the main api
```

---

### Task 6: Normalize the rule engine into parser/executor/validator/evaluator/repairer/harness layers

**Files:**
- Create: `backend/app/infrastructure/legado/engine/models.py`
- Create: `backend/app/infrastructure/legado/engine/parser.py`
- Create: `backend/app/infrastructure/legado/engine/executor.py`
- Create: `backend/app/infrastructure/legado/engine/validator.py`
- Create: `backend/app/infrastructure/legado/engine/evaluator.py`
- Create: `backend/app/infrastructure/legado/engine/repairer.py`
- Create: `backend/app/infrastructure/legado/engine/harness.py`
- Modify: `backend/app/infrastructure/legado/engine/rule_selector.py`
- Modify: `backend/app/infrastructure/legado/engine/jsonpath_ext.py`
- Test: `backend/tests/test_engine_pipeline.py`

- [ ] **Step 1: Write the failing engine pipeline tests**

```python
# backend/tests/test_engine_pipeline.py
from app.infrastructure.legado.engine.executor import execute_rule
from app.infrastructure.legado.engine.harness import run_rule_harness
from app.infrastructure.legado.engine.parser import parse_rule
from app.infrastructure.legado.engine.evaluator import evaluate_source_rules
from app.infrastructure.legado.engine.repairer import repair_source_rules
from app.infrastructure.legado.engine.validator import validate_source_rules


def test_parse_rule_detects_json_css_xpath_and_js():
    assert parse_rule("$.items[*].name").rule_type == "jsonpath"
    assert parse_rule("@css:.book-item").rule_type == "css"
    assert parse_rule("//div[@id='content']").rule_type == "xpath"
    assert parse_rule("@js:return result").rule_type == "js"


def test_validate_and_evaluate_return_structured_diagnostics():
    source = {"bookSourceName": "demo", "ruleSearch": {}, "ruleToc": {}, "ruleContent": {}}
    validation = validate_source_rules(source)
    assert validation.valid is False
    assert validation.errors

    evaluation = evaluate_source_rules(source)
    assert evaluation.score >= 0
    assert isinstance(evaluation.issues, list)


def test_repair_and_harness_return_structured_results():
    source = {"bookSourceName": "demo", "ruleSearch": "$.items[*].name", "ruleToc": "", "ruleContent": ""}
    repaired = repair_source_rules(source)
    assert repaired.changed is True
    assert repaired.updated["enabled"] is True

    parsed = parse_rule("$.items[*].name")
    execution = execute_rule(parsed, {"items": [{"name": "Book A"}]})
    assert execution.values == ["Book A"]

    harness = run_rule_harness("$.items[*].name", {"items": [{"name": "Book A"}]})
    assert harness.success is True
```

- [ ] **Step 2: Run the engine tests to verify they fail**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_engine_pipeline.py -v
```

Expected: fail because the normalized engine pipeline modules do not exist.

- [ ] **Step 3: Implement the normalized pipeline**

```python
# backend/app/infrastructure/legado/engine/models.py
from dataclasses import dataclass, field


@dataclass
class ParsedRule:
    raw: str
    rule_type: str
    expression: str
    alternatives: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    values: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class EvaluationResult:
    score: int
    grade: str
    issues: list[str] = field(default_factory=list)
    usable: bool = False


@dataclass
class RepairResult:
    changed: bool
    updated: dict
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class HarnessResult:
    success: bool
    parsed_rule: ParsedRule
    execution: ExecutionResult
    diagnostics: list[str] = field(default_factory=list)
```

```python
# backend/app/infrastructure/legado/engine/parser.py
from .models import ParsedRule


def parse_rule(raw: str) -> ParsedRule:
    rule = (raw or "").strip()
    if rule.startswith("@css:"):
        return ParsedRule(raw=raw, rule_type="css", expression=rule[5:])
    if rule.startswith("@js:"):
        return ParsedRule(raw=raw, rule_type="js", expression=rule[4:])
    if rule.startswith("//") or rule.startswith("./"):
        return ParsedRule(raw=raw, rule_type="xpath", expression=rule)
    if rule.startswith("$"):
        return ParsedRule(raw=raw, rule_type="jsonpath", expression=rule)
    return ParsedRule(raw=raw, rule_type="auto", expression=rule)
```

```python
# backend/app/infrastructure/legado/engine/executor.py
from bs4 import BeautifulSoup
from lxml import etree

from app.infrastructure.legado.engine.jsonpath_ext import run_jsonpath

from .models import ExecutionResult, ParsedRule


def execute_rule(rule: ParsedRule, sample: str | dict) -> ExecutionResult:
    if rule.rule_type == "jsonpath":
        return ExecutionResult(values=run_jsonpath(rule.expression, sample), diagnostics=[])
    if rule.rule_type == "css" and isinstance(sample, str):
        soup = BeautifulSoup(sample, "lxml")
        return ExecutionResult(values=[item.get_text(strip=True) for item in soup.select(rule.expression)], diagnostics=[])
    if rule.rule_type == "xpath" and isinstance(sample, str):
        tree = etree.HTML(sample)
        result = tree.xpath(rule.expression)
        values = [item if isinstance(item, str) else getattr(item, "text", "") for item in result]
        return ExecutionResult(values=[value for value in values if value], diagnostics=[])
    if rule.rule_type == "js":
        return ExecutionResult(values=[], diagnostics=["js rules are parsed but executed in a separate sandbox stage"])
    return ExecutionResult(values=[], diagnostics=[f"unsupported rule type: {rule.rule_type}"])
```

```python
# backend/app/infrastructure/legado/engine/validator.py
from .models import ValidationResult
from .parser import parse_rule


def validate_source_rules(source: dict) -> ValidationResult:
    missing = []
    for field in ("ruleSearch", "ruleToc", "ruleContent"):
        if not source.get(field):
            missing.append(f"missing {field}")
    warnings = []
    for field in ("ruleSearch", "ruleToc", "ruleContent"):
        value = source.get(field)
        if value:
            parsed = parse_rule(value)
            if parsed.rule_type == "auto":
                warnings.append(f"{field} uses auto-detected syntax")
    return ValidationResult(valid=not missing, errors=missing, warnings=warnings)
```

```python
# backend/app/infrastructure/legado/engine/evaluator.py
from .models import EvaluationResult
from .validator import validate_source_rules


def evaluate_source_rules(source: dict) -> EvaluationResult:
    validation = validate_source_rules(source)
    score = 100
    score -= len(validation.errors) * 30
    score -= len(validation.warnings) * 10
    score = max(score, 0)
    grade = "A" if score >= 90 else "B" if score >= 70 else "C" if score >= 50 else "D"
    return EvaluationResult(
        score=score,
        grade=grade,
        issues=validation.errors + validation.warnings,
        usable=validation.valid and score >= 70,
    )
```

```python
# backend/app/infrastructure/legado/engine/repairer.py
from copy import deepcopy

from .models import RepairResult


def repair_source_rules(source: dict) -> RepairResult:
    updated = deepcopy(source)
    diagnostics = []
    changed = False
    if "enabled" not in updated:
        updated["enabled"] = True
        diagnostics.append("added default enabled flag")
        changed = True
    for field in ("ruleToc", "ruleContent"):
        if not updated.get(field):
            updated[field] = "@css:body"
            diagnostics.append(f"filled fallback for {field}")
            changed = True
    return RepairResult(changed=changed, updated=updated, diagnostics=diagnostics)
```

```python
# backend/app/infrastructure/legado/engine/harness.py
from .executor import execute_rule
from .models import HarnessResult
from .parser import parse_rule


def run_rule_harness(raw_rule: str, sample: str | dict) -> HarnessResult:
    parsed = parse_rule(raw_rule)
    execution = execute_rule(parsed, sample)
    return HarnessResult(
        success=not execution.diagnostics,
        parsed_rule=parsed,
        execution=execution,
        diagnostics=execution.diagnostics,
    )
```

```python
# backend/app/infrastructure/legado/engine/rule_selector.py
from .executor import execute_rule
from .parser import parse_rule


def select_values(raw_rule: str, sample: str | dict) -> list[str]:
    parsed = parse_rule(raw_rule)
    result = execute_rule(parsed, sample)
    return result.values
```

```python
# backend/app/infrastructure/legado/engine/jsonpath_ext.py
from jsonpath_ng.ext import parse


def run_jsonpath(expression: str, sample: dict | list | None) -> list[str]:
    if sample is None:
        return []
    matches = parse(expression).find(sample)
    return [str(item.value) for item in matches]
```

- [ ] **Step 4: Run the engine tests**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_engine_pipeline.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Checkpoint**

Future git commit message:

```text
feat: normalize the rule engine pipeline
```

---

### Task 7: Expose engine APIs and re-home AI, translation, and novel domains under the new auth/task/audit shell

**Files:**
- Create: `backend/app/application/services/ai_service.py`
- Modify: `backend/app/application/services/translation_service.py`
- Modify: `backend/app/application/services/novel_app_service.py`
- Modify: `backend/app/application/services/novel_agent_service.py`
- Create: `backend/app/application/services/engine_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Create: `backend/app/interfaces/http/engine.py`
- Create: `backend/app/interfaces/http/ai.py`
- Create: `backend/app/interfaces/http/translation.py`
- Create: `backend/app/interfaces/http/novel.py`
- Test: `backend/tests/test_api_modules_main.py`

- [ ] **Step 1: Write the failing integration tests for engine + extended domains**

```python
# backend/tests/test_api_modules_main.py
from fastapi.testclient import TestClient

def test_engine_endpoints_are_permission_guarded(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    assert client.post("/api/engine/generate", json={"url": "https://example.com"}).status_code == 401

    token = create_access_token({"sub": "1", "permissions": ["engine.generate"], "sid": "engine-1"})
    allowed = client.post(
        "/api/engine/generate",
        json={"url": "https://example.com", "sample": {"items": [{"name": "Book A"}]}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert allowed.status_code == 200


def test_translation_ai_novel_routes_exist_under_main_api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    token = create_access_token(
        {"sub": "1", "permissions": ["translation.run", "ai.run", "novel.manage"], "sid": "modules-1"}
    )
    for path in ("/api/translation/jobs", "/api/ai/tasks", "/api/novel/books"):
        response = client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["success"] is True
```

- [ ] **Step 2: Run the tests to confirm failure**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_api_modules_main.py -v
```

Expected: fail because these new routes do not exist under the main API.

- [ ] **Step 3: Build the new engine and extended-domain route layer**

```python
# backend/app/application/services/engine_service.py
from app.infrastructure.legado.engine.evaluator import evaluate_source_rules
from app.infrastructure.legado.engine.harness import run_rule_harness
from app.infrastructure.legado.engine.repairer import repair_source_rules


class EngineService:
    async def generate(self, payload: dict) -> dict:
        return {
            "job_type": "generate",
            "input_url": payload["url"],
            "sample_present": bool(payload.get("sample")),
        }

    async def evaluate(self, payload: dict) -> dict:
        return evaluate_source_rules(payload["source"]).__dict__

    async def repair(self, payload: dict) -> dict:
        return repair_source_rules(payload["source"]).__dict__

    async def test_rule(self, payload: dict) -> dict:
        return run_rule_harness(payload["rule"], payload["sample"]).__dict__
```

```python
# backend/app/application/services/ai_service.py
class AIService:
    async def list_tasks(self) -> list[dict]:
        return [{"id": "ai-demo-1", "type": "character", "status": "idle"}]

    async def run_character_analysis(self, payload: dict) -> dict:
        return {"id": "ai-demo-2", "type": "character", "status": "queued", "input": payload}
```

```python
# backend/app/application/services/translation_service.py
class TranslationService:
    async def list_jobs(self) -> list[dict]:
        return [{"id": "tr-demo-1", "status": "idle", "source_language": "zh", "target_language": "en"}]

    async def create_job(self, payload: dict) -> dict:
        return {"id": "tr-demo-2", "status": "queued", **payload}
```

```python
# backend/app/application/services/novel_app_service.py
class NovelAppService:
    async def list_books(self) -> list[dict]:
        return [{"id": "novel-demo-1", "title": "Demo Novel", "status": "ready"}]
```

```python
# backend/app/application/services/novel_agent_service.py
class NovelAgentService:
    async def start_analysis(self, novel_id: str) -> dict:
        return {"novel_id": novel_id, "task_id": "novel-task-1", "status": "queued"}
```

```python
# backend/app/infrastructure/persistence/factory.py
from app.application.services.ai_service import AIService
from app.application.services.engine_service import EngineService
from app.application.services.novel_agent_service import NovelAgentService
from app.application.services.novel_app_service import NovelAppService
from app.application.services.translation_service import TranslationService


def build_engine_service() -> EngineService:
    return EngineService()


def build_ai_service() -> AIService:
    return AIService()


def build_translation_service() -> TranslationService:
    return TranslationService()


def build_novel_app_service() -> NovelAppService:
    return NovelAppService()


def build_novel_agent_service() -> NovelAgentService:
    return NovelAgentService()
```

```python
# backend/app/interfaces/http/engine.py
from pydantic import BaseModel
from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_engine_service
from app.interfaces.http.deps import require_permission

router = APIRouter()


class GenerateRequest(BaseModel):
    url: str
    sample: dict | None = None


class EvaluateRequest(BaseModel):
    source: dict


class RuleTestRequest(BaseModel):
    rule: str
    sample: dict | str


@router.post("/generate")
async def generate(payload: GenerateRequest, _=Depends(require_permission(Permission.ENGINE_GENERATE))):
    service = build_engine_service()
    data = await service.generate(payload.model_dump())
    return {"success": True, "code": "OK", "message": "engine generate scheduled", "data": data, "meta": {}, "trace_id": None}


@router.post("/evaluate")
async def evaluate(payload: EvaluateRequest, _=Depends(require_permission(Permission.ENGINE_EVALUATE))):
    service = build_engine_service()
    data = await service.evaluate(payload.model_dump())
    return {"success": True, "code": "OK", "message": "engine evaluation complete", "data": data, "meta": {}, "trace_id": None}


@router.post("/repair")
async def repair(payload: EvaluateRequest, _=Depends(require_permission(Permission.ENGINE_REPAIR))):
    service = build_engine_service()
    data = await service.repair(payload.model_dump())
    return {"success": True, "code": "OK", "message": "engine repair complete", "data": data, "meta": {}, "trace_id": None}

@router.post("/test")
async def test_rule(payload: RuleTestRequest, _=Depends(require_permission(Permission.ENGINE_TEST))):
    service = build_engine_service()
    data = await service.test_rule(payload.model_dump())
    return {"success": True, "code": "OK", "message": "engine harness complete", "data": data, "meta": {}, "trace_id": None}
```

```python
# backend/app/interfaces/http/translation.py
from pydantic import BaseModel
from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_translation_service
from app.interfaces.http.deps import require_permission

router = APIRouter()


class TranslationRequest(BaseModel):
    text: str
    source_language: str
    target_language: str


@router.get("/jobs")
async def list_jobs(_=Depends(require_permission(Permission.TRANSLATION_RUN))):
    service = build_translation_service()
    jobs = await service.list_jobs()
    return {"success": True, "code": "OK", "message": "translation jobs listed", "data": jobs, "meta": {"total": len(jobs)}, "trace_id": None}


@router.post("/jobs")
async def create_job(payload: TranslationRequest, _=Depends(require_permission(Permission.TRANSLATION_RUN))):
    service = build_translation_service()
    job = await service.create_job(payload.model_dump())
    return {"success": True, "code": "OK", "message": "translation job queued", "data": job, "meta": {}, "trace_id": None}
```

```python
# backend/app/interfaces/http/ai.py
from pydantic import BaseModel
from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_ai_service
from app.interfaces.http.deps import require_permission

router = APIRouter()


class CharacterAnalysisRequest(BaseModel):
    title: str
    content: str


@router.get("/tasks")
async def list_ai_tasks(_=Depends(require_permission(Permission.AI_RUN))):
    service = build_ai_service()
    tasks = await service.list_tasks()
    return {"success": True, "code": "OK", "message": "ai tasks listed", "data": tasks, "meta": {"total": len(tasks)}, "trace_id": None}


@router.post("/tasks/character")
async def run_character_analysis(
    payload: CharacterAnalysisRequest,
    _=Depends(require_permission(Permission.AI_RUN)),
):
    service = build_ai_service()
    task = await service.run_character_analysis(payload.model_dump())
    return {"success": True, "code": "OK", "message": "ai character analysis queued", "data": task, "meta": {}, "trace_id": None}
```

```python
# backend/app/interfaces/http/novel.py
from fastapi import APIRouter, Depends

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_novel_agent_service, build_novel_app_service
from app.interfaces.http.deps import require_permission

router = APIRouter()


@router.get("/books")
async def list_books(_=Depends(require_permission(Permission.NOVEL_MANAGE))):
    service = build_novel_app_service()
    books = await service.list_books()
    return {"success": True, "code": "OK", "message": "novels listed", "data": books, "meta": {"total": len(books)}, "trace_id": None}


@router.post("/books/{novel_id}/analysis")
async def analyze_book(novel_id: str, _=Depends(require_permission(Permission.NOVEL_MANAGE))):
    service = build_novel_agent_service()
    task = await service.start_analysis(novel_id)
    return {"success": True, "code": "OK", "message": "novel analysis queued", "data": task, "meta": {}, "trace_id": None}
```

- [ ] **Step 4: Run the extended-domain API tests**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_api_modules_main.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Checkpoint**

Future git commit message:

```text
feat: re-home engine ai translation and novel domains under the main api
```

---

### Task 8: Remove the legacy runtime surface, fix the install/build contract, and run the full verification matrix

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/tests/test_integration.py`
- Modify: `backend/tests/test_api_auth.py`
- Modify: `backend/tests/test_api_ai.py`
- Modify: `backend/tests/test_api_health.py`
- Retire from runtime and delete after final verification: `backend/app/interfaces/api/v0/*`, `backend/app/interfaces/api/v1/*`, `backend/app/api/routers/*`, `backend/app/routers/*`

- [ ] **Step 1: Replace or retire the legacy tests that encode the old runtime assumptions**

```python
# backend/tests/test_integration.py
def test_legacy_v0_surface_is_not_mounted_anymore(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    assert client.get("/api/sources/book").status_code == 404


def test_main_api_status_is_public(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    assert client.get("/api/status").status_code == 200
```

```python
# backend/tests/test_api_auth.py
from fastapi.testclient import TestClient


def test_legacy_login_path_is_gone(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.main import app

    client = TestClient(app)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123456"}).status_code == 404
```

```python
# backend/tests/test_api_ai.py
from fastapi.testclient import TestClient

def test_ai_routes_live_under_main_api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    token = create_access_token({"sub": "1", "permissions": ["ai.run"], "sid": "ai-legacy-1"})
    response = client.get("/api/ai/tasks", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
```

```python
# backend/tests/test_api_health.py
from fastapi.testclient import TestClient

def test_health_requires_auth_except_status(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/health").status_code == 401

    token = create_access_token({"sub": "1", "permissions": ["health.check"], "sid": "health-1"})
    assert client.get("/api/health", headers={"Authorization": f"Bearer {token}"}).status_code == 200
```

- [ ] **Step 2: Repair the dependency contract for local Python 3.13**

```text
# backend/requirements.txt
fastapi==0.111.0
uvicorn[standard]==0.30.0
sqlalchemy>=2.0.36
pydantic>=2.7,<3
pydantic-settings>=2.2,<3
httpx==0.27.0
aiohttp>=3.10
beautifulsoup4==4.12.3
lxml>=5.2
feedparser==6.0.11
apscheduler==3.10.4
python-multipart==0.0.9
jinja2==3.1.4
aiofiles==23.2.0
pytest==8.2.0
pytest-asyncio==0.23.7
passlib[bcrypt]==1.7.4
python-jose[cryptography]==3.3.0
redis==5.0.4
jsonpath-ng>=1.7.0
ply>=3.11
```

- [ ] **Step 3: Run the targeted verification commands**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest tests\test_runtime_bootstrap.py tests\test_core_security_main.py tests\test_rbac_permissions.py tests\test_auth_repo_sqlite.py tests\test_api_auth_main.py tests\test_api_admin_rbac.py tests\test_api_sources_main.py tests\test_api_dashboard_export.py tests\test_engine_pipeline.py tests\test_api_modules_main.py -v
```

Expected: all 10 target test modules pass with zero failures.

- [ ] **Step 4: Run the local startup smoke verification**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
$env:APP_ENV='dev'
$env:SECRET_KEY='local-dev-secret-key-32-bytes-minimum'
$env:DB_PATH='C:\Users\lihuo\Desktop\legado-hub\backend\data\main_api.sqlite3'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected:
- `GET /api/status` returns 200 without auth
- `GET /api/export/book_sources` returns 401 without auth
- `POST /api/auth/login` returns access + refresh
- authenticated calls to `/api/admin/*`, `/api/sources/*`, `/api/engine/*` succeed for a privileged user

- [ ] **Step 5: Checkpoint**

Future git commit message:

```text
refactor: remove legacy runtime surface and verify python 3.13 main api stack
```

---

## Spec Coverage Check

- New single runtime shell: covered by Task 1 and Task 8
- Access + refresh auth model: covered by Task 2, Task 3, Task 4
- Full RBAC: covered by Task 2, Task 3, Task 4
- Rebuilt SQLite schema: covered by Task 3 and exercised again by Task 5 and Task 7
- Sources/export/dashboard/health mainline: covered by Task 5
- Rule engine normalization: covered by Task 6 and Task 7
- AI / translation / novel stable re-homing: covered by Task 7
- Python 3.13 reproducibility: covered by Task 8

## Placeholder Scan

- Searched the saved plan for ellipsis-only stub bodies and common placeholder markers; none remain in executable snippets.
- Contract-only abstractions use explicit `raise NotImplementedError` bodies, and every route snippet now returns a concrete response shape.

## Type Consistency Check

- Main API routes live under `/api/*`, not `/api/v1/*`.
- Permission names use `resource.action`.
- Pagination stays in `meta`.
- Export is authenticated.
- Status is public.

## Completion Criteria

- [ ] Only the new main API is mounted at runtime
- [ ] `/api/status` is public and other main routes are authenticated
- [ ] Passwords use bcrypt instead of SHA256 + secret
- [ ] Access + refresh + API key flows work
- [ ] Full RBAC covers core and extended domains
- [ ] Sources/export/dashboard/health use the new contracts
- [ ] Rule engine has normalized parse/execute/validate/evaluate/repair/test layers
- [ ] AI / translation / novel operate under the new auth/task/audit shell
- [ ] Backend runs locally on Python 3.13 with SQLite from declared dependencies
