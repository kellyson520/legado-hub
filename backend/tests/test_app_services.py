"""当前应用服务公开契约的回归测试。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.application.services.auth_service import AuthAppService
from app.application.services.source_service import SourceAppService
from app.core.exceptions import AuthenticationException, ValidationException
from app.core.security import verify_password
from app.domain.entities.auth import ApiKey, AuditEvent, RefreshSession, User


class FakeAuthRepository:
    """仅实现 AuthAppService 当前测试路径需要的仓储协议。"""

    def __init__(self):
        self.users: dict[int, User] = {}
        self.sessions: dict[str, RefreshSession] = {}
        self.api_keys: dict[int, ApiKey] = {}
        self.audit_events: list[AuditEvent] = []
        self._next_user_id = 1
        self._next_api_key_id = 1
        self._next_audit_id = 1

    async def get_user_by_username(self, username: str) -> User | None:
        return next((item for item in self.users.values() if item.username == username), None)

    async def save_user(self, user: User) -> User:
        user.id = self._next_user_id
        self._next_user_id += 1
        self.users[user.id] = user
        return user

    async def list_users(self) -> list[User]:
        return list(self.users.values())

    async def get_user_by_id(self, user_id: int) -> User | None:
        return self.users.get(user_id)

    async def update_user(
        self,
        user_id: int,
        *,
        display_name: str | None = None,
        password_hash: str | None = None,
        is_active: bool | None = None,
        role_names: list[str] | None = None,
        last_login_at=None,
    ) -> User | None:
        user = self.users.get(user_id)
        if user is None:
            return None
        if display_name is not None:
            user.display_name = display_name
        if password_hash is not None:
            user.password_hash = password_hash
        if is_active is not None:
            user.is_active = is_active
        if role_names is not None:
            user.role_names = list(role_names)
        if last_login_at is not None:
            user.last_login_at = last_login_at
        return user

    async def assign_roles(self, user_id: int, role_names: list[str]) -> None:
        self.users[user_id].role_names = list(role_names)

    async def get_permissions_for_user(self, user_id: int) -> list[str]:
        return list(self.users[user_id].permissions)

    async def save_refresh_session(self, session: RefreshSession) -> RefreshSession:
        self.sessions[session.id] = session
        return session

    async def get_refresh_session(self, session_id: str) -> RefreshSession | None:
        return self.sessions.get(session_id)

    async def revoke_refresh_session(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if session is not None:
            session.revoked_at = datetime.now(timezone.utc)

    async def revoke_all_refresh_sessions(self, user_id: int) -> None:
        for session in self.sessions.values():
            if session.user_id == user_id:
                session.revoked_at = datetime.now(timezone.utc)

    async def save_api_key(self, api_key: ApiKey) -> ApiKey:
        api_key.id = self._next_api_key_id
        self._next_api_key_id += 1
        self.api_keys[api_key.id] = api_key
        return api_key

    async def list_api_keys(self) -> list[ApiKey]:
        return list(self.api_keys.values())

    async def set_api_key_enabled(self, api_key_id: int, enabled: bool) -> None:
        self.api_keys[api_key_id].is_enabled = enabled

    async def delete_api_key(self, api_key_id: int) -> None:
        self.api_keys.pop(api_key_id, None)

    async def record_audit(self, event: AuditEvent) -> AuditEvent:
        event.id = self._next_audit_id
        self._next_audit_id += 1
        self.audit_events.append(event)
        return event


class FakeSourceRepository:
    """仅实现 SourceAppService 当前测试路径需要的仓储协议。"""

    def __init__(self):
        self.items: dict[int, dict] = {}
        self.upserted_urls: list[str] = []
        self._next_id = 1

    async def list_book_sources(self, page: int, page_size: int, enabled_only: bool = False):
        items = list(self.items.values())
        if enabled_only:
            items = [item for item in items if item.get("enabled", True)]
        total = len(items)
        start = (page - 1) * page_size
        return [dict(item) for item in items[start : start + page_size]], total

    async def create_book_source(self, data: dict, actor_id: int) -> dict:
        item = {**data, "id": self._next_id}
        self._next_id += 1
        self.items[item["id"]] = item
        return dict(item)

    async def update_book_source(self, source_id: int, data: dict, actor_id: int) -> dict:
        self.items[source_id].update(data)
        return dict(self.items[source_id])

    async def delete_book_source(self, source_id: int, actor_id: int) -> None:
        del self.items[source_id]

    async def export_book_sources(self, enabled_only: bool = False) -> list[dict]:
        items = list(self.items.values())
        if enabled_only:
            items = [item for item in items if item.get("enabled", True)]
        return [dict(item) for item in items]

    async def list_book_sources_full(
        self,
        enabled_only: bool = False,
        ids: list[int] | None = None,
        urls: list[str] | None = None,
    ) -> list[dict]:
        items = await self.export_book_sources(enabled_only=enabled_only)
        if ids is not None:
            items = [item for item in items if item["id"] in ids]
        if urls is not None:
            items = [item for item in items if item["bookSourceUrl"] in urls]
        return items

    async def upsert_book_sources(self, items: list[dict], actor_id: int) -> int:
        self.upserted_urls = [item["bookSourceUrl"] for item in items]
        existing_by_url = {item["bookSourceUrl"]: item for item in self.items.values()}
        for data in items:
            existing = existing_by_url.get(data["bookSourceUrl"])
            if existing is not None:
                existing.update(data)
            else:
                await self.create_book_source(data, actor_id)
        return len(items)


@pytest.fixture
def auth_repo():
    return FakeAuthRepository()


@pytest.fixture
def auth_service(auth_repo):
    return AuthAppService(auth_repo)


@pytest.fixture
def source_repo():
    return FakeSourceRepository()


@pytest.fixture
def source_service(source_repo):
    return SourceAppService(source_repo)


class TestAuthAppService:
    async def test_create_user_admin_assigns_requested_role(self, auth_service, auth_repo):
        created = await auth_service.create_user_admin(
            "reader", "Reader", "user", "password-123", actor_id=9
        )

        assert created["username"] == "reader"
        assert created["display_name"] == "Reader"
        assert created["role"] == "user"
        assert auth_repo.users[created["id"]].role_names == ["user"]
        assert auth_repo.audit_events[-1].action == "user.create"

    async def test_create_user_admin_rejects_unsupported_role(self, auth_service):
        with pytest.raises(ValidationException, match="Unsupported user role"):
            await auth_service.create_user_admin(
                "reader", "Reader", "operator", "password-123", actor_id=1
            )

    async def test_create_user_admin_rejects_duplicate_username(self, auth_service):
        await auth_service.create_user_admin("reader", "Reader", "user", "password-123", actor_id=1)

        with pytest.raises(ValidationException, match="Username already exists"):
            await auth_service.create_user_admin("reader", "Another", "user", "password-456", actor_id=1)

    async def test_list_users_serializes_current_user_contract(self, auth_service):
        await auth_service.create_user_admin("admin", "Admin", "admin", "password-123", actor_id=1)
        await auth_service.create_user_admin("reader", "Reader", "user", "password-123", actor_id=1)

        users = await auth_service.list_users()

        assert [(item["username"], item["role"], item["status"]) for item in users] == [
            ("admin", "admin", "enabled"),
            ("reader", "user", "enabled"),
        ]

    async def test_disabling_last_enabled_admin_is_rejected(self, auth_service, auth_repo):
        admin = await auth_service.create_user_admin("admin", "Admin", "admin", "password-123", actor_id=1)

        with pytest.raises(ValidationException, match="last enabled administrator"):
            await auth_service.set_user_enabled_admin(admin["id"], enabled=False, actor_id=2)

        assert auth_repo.users[admin["id"]].is_active is True

    async def test_disabling_user_revokes_all_refresh_sessions(self, auth_service, auth_repo):
        await auth_service.create_user_admin("admin", "Admin", "admin", "password-123", actor_id=1)
        reader = await auth_service.create_user_admin("reader", "Reader", "user", "password-123", actor_id=1)
        await auth_repo.save_refresh_session(RefreshSession(id="reader-session", user_id=reader["id"]))

        updated = await auth_service.set_user_enabled_admin(reader["id"], enabled=False, actor_id=1)

        assert updated["status"] == "disabled"
        assert auth_repo.sessions["reader-session"].revoked_at is not None
        assert auth_repo.audit_events[-1].action == "user.disable"

    async def test_reset_password_revokes_target_sessions(self, auth_service, auth_repo):
        reader = await auth_service.create_user_admin("reader", "Reader", "user", "password-123", actor_id=1)
        await auth_repo.save_refresh_session(RefreshSession(id="reader-session", user_id=reader["id"]))

        await auth_service.reset_password_admin(reader["id"], "new-password-456", actor_id=9)

        assert verify_password("new-password-456", auth_repo.users[reader["id"]].password_hash)
        assert auth_repo.sessions["reader-session"].revoked_at is not None
        assert auth_repo.audit_events[-1].action == "user.password_reset"

    async def test_api_key_lifecycle_returns_raw_key_and_records_audits(self, auth_service, auth_repo):
        created = await auth_service.create_api_key("reader-key", ["sources:read"], actor_id=9)

        assert created["name"] == "reader-key"
        assert created["permissions"] == ["sources:read"]
        assert created["raw_key"]
        assert created["raw_key"] != created["key_hash"]

        await auth_service.set_api_key_enabled(created["id"], enabled=False, actor_id=9)
        assert (await auth_service.list_api_keys()) == [
            {key: value for key, value in created.items() if key != "raw_key"} | {"is_enabled": False}
        ]

        await auth_service.delete_api_key(created["id"], actor_id=9)
        assert await auth_service.list_api_keys() == []
        assert [event.action for event in auth_repo.audit_events] == [
            "api_key.create",
            "api_key.update",
            "api_key.delete",
        ]

    async def test_login_persists_session_and_logout_revokes_it(self, auth_service, auth_repo):
        reader = await auth_service.create_user_admin("reader", "Reader", "user", "password-123", actor_id=1)
        auth_repo.users[reader["id"]].permissions = ["sources:read"]

        tokens = await auth_service.login("reader", "password-123")

        assert tokens["token_type"] == "bearer"
        assert tokens["permissions"] == ["sources:read"]
        assert tokens["access_token"]
        assert tokens["refresh_token"]
        session_id = next(iter(auth_repo.sessions))
        assert auth_repo.users[reader["id"]].last_login_at is not None

        await auth_service.logout(session_id, actor_id=reader["id"])

        assert auth_repo.sessions[session_id].revoked_at is not None
        assert [event.action for event in auth_repo.audit_events[-2:]] == ["auth.login", "auth.logout"]

    @pytest.mark.parametrize(
        ("username", "password"),
        [("nobody", "password-123"), ("reader", "wrong-password")],
    )
    async def test_login_rejects_invalid_credentials(self, auth_service, username, password):
        await auth_service.create_user_admin("reader", "Reader", "user", "password-123", actor_id=1)

        with pytest.raises(AuthenticationException, match="Invalid username or password"):
            await auth_service.login(username, password)


class TestSourceAppService:
    async def test_list_book_sources_returns_requested_page_metadata(self, source_service, source_repo):
        await source_repo.create_book_source(
            {"bookSourceUrl": "https://one.example", "bookSourceName": "One"}, actor_id=1
        )
        await source_repo.create_book_source(
            {"bookSourceUrl": "https://two.example", "bookSourceName": "Two"}, actor_id=1
        )

        result = await source_service.list_book_sources(page=2, page_size=1)

        assert result["meta"] == {"page": 2, "page_size": 1, "total": 2, "total_pages": 2}
        assert [item["bookSourceUrl"] for item in result["items"]] == ["https://two.example"]

    async def test_create_update_and_delete_book_source_delegate_current_crud_contract(
        self, source_service
    ):
        created = await source_service.create_book_source(
            {"bookSourceUrl": "https://book.example", "bookSourceName": "Book", "enabled": True},
            actor_id=8,
        )
        updated = await source_service.update_book_source(
            created["id"], {"bookSourceName": "Updated", "enabled": False}, actor_id=8
        )

        assert updated["bookSourceName"] == "Updated"
        assert updated["enabled"] is False

        await source_service.delete_book_source(created["id"], actor_id=8)
        assert (await source_service.list_book_sources(page=1, page_size=10))["items"] == []

    async def test_export_book_sources_counts_enabled_sources(self, source_service, source_repo):
        await source_repo.create_book_source(
            {"bookSourceUrl": "https://enabled.example", "bookSourceName": "Enabled", "enabled": True},
            actor_id=1,
        )
        await source_repo.create_book_source(
            {"bookSourceUrl": "https://disabled.example", "bookSourceName": "Disabled", "enabled": False},
            actor_id=1,
        )

        result = await source_service.export_book_sources(enabled_only=True)

        assert result["count"] == 1
        assert [item["bookSourceUrl"] for item in result["items"]] == ["https://enabled.example"]

    async def test_import_book_sources_skips_existing_urls_when_requested(
        self, source_service, source_repo, tmp_path
    ):
        await source_repo.create_book_source(
            {"bookSourceUrl": "https://existing.example", "bookSourceName": "Existing"}, actor_id=1
        )
        source_file = tmp_path / "sources.json"
        source_file.write_text(
            json.dumps(
                [
                    {"bookSourceUrl": "https://existing.example", "bookSourceName": "Existing update"},
                    {"bookSourceUrl": "https://new.example", "bookSourceName": "New"},
                ]
            ),
            encoding="utf-8",
        )

        result = await source_service.import_book_sources_from_file(
            str(source_file), actor_id=8, replace_existing=False
        )

        assert result == {"file_path": str(source_file), "book_count": 1}
        assert source_repo.upserted_urls == ["https://new.example"]
        assert [item["bookSourceUrl"] for item in await source_repo.export_book_sources()] == [
            "https://existing.example",
            "https://new.example",
        ]
