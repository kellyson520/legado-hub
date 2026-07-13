"""
测试应用层服务: AuthAppService 和 SourceAppService

测试范围:
- AuthAppService: 管理员初始化、登录认证、用户管理、API Key 管理、配额与审计日志
- SourceAppService: 书源的 CRUD、导出、事件发布
- 使用内存 Mock 仓储，不依赖真实数据库
- 覆盖正常路径和异常路径
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from app.domain.entities.user import User, ApiKey, AuditLog, QuotaUsage
from app.domain.entities.source import BookSource, RssSource, Subscription, FilterRule
from app.domain.repositories.user_repo import UserRepository
from app.domain.repositories.source_repo import SourceRepository
from app.application.services.auth_service import AuthAppService
from app.application.services.source_service import SourceAppService
from app.core.exceptions import (
    AuthenticationException, ConflictException, NotFoundException
)


# ==================== Mock 仓储 ====================

class MockUserRepository(UserRepository):
    """用户仓储 Mock 实现 — 内部用字典存储，支持异步调用"""

    def __init__(self):
        self._users: Dict[int, User] = {}
        self._users_by_username: Dict[str, User] = {}
        self._api_keys: Dict[int, ApiKey] = {}
        self._api_keys_by_hash: Dict[str, ApiKey] = {}
        self._audit_logs: List[AuditLog] = []
        self._quota_usages: Dict[tuple, QuotaUsage] = {}
        self._next_user_id = 1
        self._next_api_key_id = 1
        self._next_audit_id = 1

    # ---------- User ----------

    async def get_user(self, user_id: int) -> Optional[User]:
        return self._users.get(user_id)

    async def get_user_by_username(self, username: str) -> Optional[User]:
        return self._users_by_username.get(username)

    async def list_users(self, page: int = 1, page_size: int = 50) -> tuple[List[User], int]:
        all_users = list(self._users.values())
        return all_users, len(all_users)

    async def save_user(self, user: User) -> User:
        # 模拟自增 ID
        if user.id == 0:
            user.id = self._next_user_id
            self._next_user_id += 1
        self._users[user.id] = user
        self._users_by_username[user.username] = user
        return user

    async def delete_user(self, user_id: int) -> bool:
        user = self._users.pop(user_id, None)
        if user:
            self._users_by_username.pop(user.username, None)
            return True
        return False

    # ---------- ApiKey ----------

    async def get_api_key_by_hash(self, key_hash: str) -> Optional[ApiKey]:
        return self._api_keys_by_hash.get(key_hash)

    async def get_api_key(self, key_id: int) -> Optional[ApiKey]:
        return self._api_keys.get(key_id)

    async def list_api_keys(self, user_id: Optional[int] = None) -> List[ApiKey]:
        return list(self._api_keys.values())

    async def save_api_key(self, key: ApiKey) -> ApiKey:
        if key.id == 0:
            key.id = self._next_api_key_id
            self._next_api_key_id += 1
        self._api_keys[key.id] = key
        if key.key_hash:
            self._api_keys_by_hash[key.key_hash] = key
        return key

    async def delete_api_key(self, key_id: int) -> bool:
        key = self._api_keys.pop(key_id, None)
        if key:
            self._api_keys_by_hash.pop(key.key_hash, None)
            return True
        return False

    async def update_api_key_last_used(self, key_id: int) -> bool:
        key = self._api_keys.get(key_id)
        if key:
            key.last_used_at = datetime.utcnow()
            return True
        return False

    # ---------- AuditLog ----------

    async def list_audit_logs(
        self,
        action: Optional[str] = None,
        api_key_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 50
    ) -> tuple[List[AuditLog], int]:
        return self._audit_logs, len(self._audit_logs)

    async def save_audit_log(self, log: AuditLog) -> AuditLog:
        if log.id == 0:
            log.id = self._next_audit_id
            self._next_audit_id += 1
        self._audit_logs.append(log)
        return log

    async def delete_old_audit_logs(self, days: int = 90) -> int:
        before = len(self._audit_logs)
        self._audit_logs.clear()
        return before

    # ---------- QuotaUsage ----------

    async def get_quota_usage(self, api_key_id: int, date: str) -> Optional[QuotaUsage]:
        return self._quota_usages.get((api_key_id, date))

    async def save_quota_usage(self, usage: QuotaUsage) -> QuotaUsage:
        self._quota_usages[(usage.api_key_id, usage.date)] = usage
        return usage


class MockSourceRepository(SourceRepository):
    """源仓储 Mock 实现 — 内部用字典存储"""

    def __init__(self):
        self._book_sources: Dict[str, BookSource] = {}
        self._rss_sources: Dict[str, RssSource] = {}
        self._subscriptions: Dict[int, Subscription] = {}
        self._filter_rules: Dict[int, FilterRule] = {}
        self._next_sub_id = 1
        self._next_rule_id = 1

    # ---------- BookSource ----------

    async def get_book_source(self, url: str) -> Optional[BookSource]:
        return self._book_sources.get(url)

    async def list_book_sources(
        self,
        group: Optional[str] = None,
        status: Optional[str] = None,
        enabled_only: bool = False,
        page: int = 1,
        page_size: int = 50
    ) -> tuple[List[BookSource], int]:
        sources = list(self._book_sources.values())
        return sources, len(sources)

    async def save_book_source(self, source: BookSource) -> BookSource:
        self._book_sources[source.bookSourceUrl] = source
        return source

    async def save_book_sources(self, sources: List[BookSource]) -> int:
        for s in sources:
            self._book_sources[s.bookSourceUrl] = s
        return len(sources)

    async def delete_book_source(self, url: str) -> bool:
        return self._book_sources.pop(url, None) is not None

    async def update_book_source_status(self, url: str, status: str, error_msg: Optional[str] = None) -> bool:
        source = self._book_sources.get(url)
        if source:
            source.sourceStatus = status
            source.errorMsg = error_msg
            return True
        return False

    # ---------- RssSource ----------

    async def get_rss_source(self, url: str) -> Optional[RssSource]:
        return self._rss_sources.get(url)

    async def list_rss_sources(
        self,
        group: Optional[str] = None,
        status: Optional[str] = None,
        enabled_only: bool = False,
        page: int = 1,
        page_size: int = 50
    ) -> tuple[List[RssSource], int]:
        sources = list(self._rss_sources.values())
        return sources, len(sources)

    async def save_rss_source(self, source: RssSource) -> RssSource:
        self._rss_sources[source.sourceUrl] = source
        return source

    async def save_rss_sources(self, sources: List[RssSource]) -> int:
        for s in sources:
            self._rss_sources[s.sourceUrl] = s
        return len(sources)

    async def delete_rss_source(self, url: str) -> bool:
        return self._rss_sources.pop(url, None) is not None

    async def update_rss_source_status(self, url: str, status: str, error_msg: Optional[str] = None) -> bool:
        source = self._rss_sources.get(url)
        if source:
            source.sourceStatus = status
            source.errorMsg = error_msg
            return True
        return False

    # ---------- Subscription ----------

    async def get_subscription(self, sub_id: int) -> Optional[Subscription]:
        return self._subscriptions.get(sub_id)

    async def list_subscriptions(self, enabled_only: bool = False) -> List[Subscription]:
        return list(self._subscriptions.values())

    async def save_subscription(self, sub: Subscription) -> Subscription:
        if sub.id == 0:
            sub.id = self._next_sub_id
            self._next_sub_id += 1
        self._subscriptions[sub.id] = sub
        return sub

    async def delete_subscription(self, sub_id: int) -> bool:
        return self._subscriptions.pop(sub_id, None) is not None

    # ---------- FilterRule ----------

    async def list_filter_rules(self, enabled_only: bool = True) -> List[FilterRule]:
        return list(self._filter_rules.values())

    async def save_filter_rule(self, rule: FilterRule) -> FilterRule:
        if rule.id == 0:
            rule.id = self._next_rule_id
            self._next_rule_id += 1
        self._filter_rules[rule.id] = rule
        return rule

    async def delete_filter_rule(self, rule_id: int) -> bool:
        return self._filter_rules.pop(rule_id, None) is not None


# ==================== fixtures ====================

@pytest.fixture
def mock_user_repo():
    """创建空的 MockUserRepository"""
    return MockUserRepository()


@pytest.fixture
def mock_source_repo():
    """创建空的 MockSourceRepository"""
    return MockSourceRepository()


@pytest.fixture
def auth_service(mock_user_repo):
    """创建 AuthAppService 实例，注入 Mock 仓储"""
    return AuthAppService(mock_user_repo)


@pytest.fixture
def source_service(mock_source_repo):
    """创建 SourceAppService 实例，注入 Mock 仓储"""
    return SourceAppService(mock_source_repo)


# ==================== AuthAppService 测试 ====================

class TestAuthAppServiceSetupAdmin:
    """测试管理员初始化逻辑"""

    @pytest.mark.asyncio
    async def test_setup_admin_创建新管理员(self, auth_service, mock_user_repo):
        # 正常路径：首次创建管理员
        user = await auth_service.setup_admin("admin", "secret123")
        assert user.username == "admin"
        assert user.role == "admin"
        assert user.id > 0
        assert user.password_hash is not None

    @pytest.mark.asyncio
    async def test_setup_admin_已存在则抛出冲突异常(self, auth_service):
        # 异常路径：重复创建管理员
        await auth_service.setup_admin("admin", "secret123")
        with pytest.raises(ConflictException, match="管理员已存在"):
            await auth_service.setup_admin("admin", "another_pwd")


class TestAuthAppServiceLogin:
    """测试登录认证逻辑"""

    @pytest.mark.asyncio
    async def test_login_成功返回token(self, auth_service):
        # 先创建管理员
        await auth_service.setup_admin("admin", "secret123")
        # 正常登录
        token = await auth_service.login("admin", "secret123")
        assert isinstance(token, str)
        assert len(token) > 0

    @pytest.mark.asyncio
    async def test_login_用户不存在抛出异常(self, auth_service):
        # 异常路径：用户不存在
        with pytest.raises(AuthenticationException, match="用户名或密码错误"):
            await auth_service.login("nobody", "whatever")

    @pytest.mark.asyncio
    async def test_login_密码错误抛出异常(self, auth_service):
        # 异常路径：密码错误
        await auth_service.setup_admin("admin", "secret123")
        with pytest.raises(AuthenticationException, match="用户名或密码错误"):
            await auth_service.login("admin", "wrong_password")


class TestAuthAppServiceUserManagement:
    """测试用户查询与管理"""

    @pytest.mark.asyncio
    async def test_get_user_存在时返回(self, auth_service, mock_user_repo):
        # 预置一个用户
        user = User(id=1, username="testuser", role="user")
        mock_user_repo._users[1] = user
        mock_user_repo._users_by_username["testuser"] = user

        result = await auth_service.get_user(1)
        assert result is not None
        assert result.username == "testuser"

    @pytest.mark.asyncio
    async def test_get_user_不存在返回None(self, auth_service):
        result = await auth_service.get_user(999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_by_username_存在时返回(self, auth_service):
        await auth_service.setup_admin("admin", "secret123")
        result = await auth_service.get_user_by_username("admin")
        assert result is not None
        assert result.role == "admin"

    @pytest.mark.asyncio
    async def test_get_user_by_username_不存在返回None(self, auth_service):
        result = await auth_service.get_user_by_username("ghost")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_users_返回用户列表(self, auth_service):
        await auth_service.setup_admin("admin", "secret123")
        users, total = await auth_service.list_users()
        assert isinstance(users, list)
        assert total >= 1

    @pytest.mark.asyncio
    async def test_list_users_自定义分页参数(self, auth_service):
        # 即使空仓储也能正常返回
        users, total = await auth_service.list_users(page=2, page_size=10)
        assert users == []
        assert total == 0


class TestAuthAppServiceApiKeyManagement:
    """测试 API Key 管理"""

    @pytest.mark.asyncio
    async def test_create_api_key_返回原始key和实体(self, auth_service):
        raw_key, key_entity = await auth_service.create_api_key("test-key")
        # 原始 key 以 lh_ 开头
        assert raw_key.startswith("lh_")
        assert len(raw_key) > 10
        # 实体
        assert key_entity.id > 0
        assert key_entity.name == "test-key"
        assert key_entity.key_hash != ""

    @pytest.mark.asyncio
    async def test_create_api_key_自定义权限(self, auth_service):
        permissions = {"source_read": True, "export": False, "admin": True}
        raw_key, key_entity = await auth_service.create_api_key(
            "custom-key", permissions=permissions
        )
        assert key_entity.permissions == permissions

    @pytest.mark.asyncio
    async def test_create_api_key_默认权限(self, auth_service):
        _, key_entity = await auth_service.create_api_key("default-key")
        # 默认权限
        assert key_entity.permissions is not None
        assert key_entity.permissions.get("source_read") is True
        assert key_entity.permissions.get("export") is True

    @pytest.mark.asyncio
    async def test_list_api_keys_空列表(self, auth_service):
        keys = await auth_service.list_api_keys()
        assert keys == []

    @pytest.mark.asyncio
    async def test_list_api_keys_创建后返回(self, auth_service):
        await auth_service.create_api_key("key1")
        await auth_service.create_api_key("key2")
        keys = await auth_service.list_api_keys()
        assert len(keys) == 2

    @pytest.mark.asyncio
    async def test_delete_api_key_存在时返回True(self, auth_service):
        _, key_entity = await auth_service.create_api_key("to-delete")
        result = await auth_service.delete_api_key(key_entity.id)
        assert result is True
        # 删除后列表为空
        keys = await auth_service.list_api_keys()
        assert len(keys) == 0

    @pytest.mark.asyncio
    async def test_delete_api_key_不存在时返回False(self, auth_service):
        result = await auth_service.delete_api_key(9999)
        assert result is False


class TestAuthAppServiceQuotaAndAudit:
    """测试配额和审计日志"""

    @pytest.mark.asyncio
    async def test_get_quota_不存在返回None(self, auth_service):
        result = await auth_service.get_quota(1, "2026-01-01")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_and_get_quota(self, auth_service):
        usage = QuotaUsage(
            api_key_id=1,
            date="2026-01-01",
            fetch_count=100,
            ai_chars=5000,
        )
        saved = await auth_service.save_quota(usage)
        result = await auth_service.get_quota(1, "2026-01-01")
        assert result is not None
        assert result.fetch_count == 100

    @pytest.mark.asyncio
    async def test_list_audit_logs_空列表(self, auth_service):
        logs, total = await auth_service.list_audit_logs()
        assert logs == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_save_and_list_audit_logs(self, auth_service):
        log = AuditLog(
            action="login",
            resource_type="user",
            details={"ip": "127.0.0.1"},
        )
        await auth_service.save_audit_log(log)
        logs, total = await auth_service.list_audit_logs()
        assert total == 1
        assert logs[0].action == "login"

    @pytest.mark.asyncio
    async def test_list_audit_logs_带过滤参数(self, auth_service):
        # 即使过滤条件无匹配也应返回空列表而非报错
        logs, total = await auth_service.list_audit_logs(action="nonexistent")
        assert logs == []

    @pytest.mark.asyncio
    async def test_archive_old_logs(self, auth_service):
        await auth_service.save_audit_log(AuditLog(action="test"))
        deleted_count = await auth_service.archive_old_logs(days=90)
        assert deleted_count >= 0


# ==================== SourceAppService 测试 ====================

class TestSourceAppServiceBookSourceCRUD:
    """测试书源的增删改查"""

    @pytest.mark.asyncio
    async def test_list_book_sources_空列表(self, source_service):
        sources, total = await source_service.list_book_sources()
        assert sources == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_book_sources_分页参数透传(self, source_service):
        sources, total = await source_service.list_book_sources(
            enabled_only=True, page=2, page_size=5
        )
        # 空仓储，返回空
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_book_source_存在时返回(self, source_service, mock_source_repo):
        # 预置书源
        source = BookSource(
            bookSourceUrl="https://example.com",
            bookSourceName="测试书源",
        )
        mock_source_repo._book_sources["https://example.com"] = source

        result = await source_service.get_book_source("https://example.com")
        assert result is not None
        assert result.bookSourceName == "测试书源"

    @pytest.mark.asyncio
    async def test_get_book_source_不存在抛出异常(self, source_service):
        with pytest.raises(NotFoundException, match="书源不存在"):
            await source_service.get_book_source("https://not-exist.com")

    @pytest.mark.asyncio
    async def test_create_book_source_成功(self, source_service):
        data = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "新建书源",
            "bookSourceGroup": "测试",
        }
        result = await source_service.create_book_source(data)
        assert result.bookSourceUrl == "https://example.com"
        assert result.bookSourceName == "新建书源"

    @pytest.mark.asyncio
    async def test_update_book_source_成功(self, source_service):
        # 先创建
        data = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "原名",
        }
        await source_service.create_book_source(data)

        # 更新
        updated = await source_service.update_book_source(
            "https://example.com",
            {"bookSourceName": "新名"},
        )
        assert updated.bookSourceName == "新名"

    @pytest.mark.asyncio
    async def test_update_book_source_不存在抛出异常(self, source_service):
        with pytest.raises(NotFoundException, match="书源不存在"):
            await source_service.update_book_source(
                "https://not-exist.com", {"bookSourceName": "xxx"}
            )

    @pytest.mark.asyncio
    async def test_delete_book_source_成功(self, source_service):
        data = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "待删除",
        }
        await source_service.create_book_source(data)

        result = await source_service.delete_book_source("https://example.com")
        assert result is True

        # 删除后再查应抛异常
        with pytest.raises(NotFoundException):
            await source_service.get_book_source("https://example.com")

    @pytest.mark.asyncio
    async def test_delete_book_source_不存在抛出异常(self, source_service):
        with pytest.raises(NotFoundException, match="书源不存在"):
            await source_service.delete_book_source("https://not-exist.com")


class TestSourceAppServiceExport:
    """测试导出功能"""

    @pytest.mark.asyncio
    async def test_export_book_sources_空列表(self, source_service):
        result = await source_service.export_book_sources()
        assert result == []

    @pytest.mark.asyncio
    async def test_export_book_sources_有数据时返回字典列表(self, source_service):
        await source_service.create_book_source({
            "bookSourceUrl": "https://a.com",
            "bookSourceName": "书源A",
        })
        result = await source_service.export_book_sources()
        assert len(result) == 1
        # 导出应为字典格式，不含内部字段
        assert "bookSourceUrl" in result[0]
        assert result[0]["bookSourceUrl"] == "https://a.com"

    @pytest.mark.asyncio
    async def test_export_all_sources_返回完整结构(self, source_service):
        await source_service.create_book_source({
            "bookSourceUrl": "https://book.com",
            "bookSourceName": "书源",
        })
        await source_service.create_rss_source({
            "sourceUrl": "https://rss.com",
            "sourceName": "RSS源",
        })

        result = await source_service.export_all_sources()
        assert "bookSources" in result
        assert "rssSources" in result
        assert "totalBookSources" in result
        assert "totalRssSources" in result
        assert result["totalBookSources"] == 1
        assert result["totalRssSources"] == 1

    @pytest.mark.asyncio
    async def test_export_all_sources_空数据(self, source_service):
        result = await source_service.export_all_sources()
        assert result["totalBookSources"] == 0
        assert result["totalRssSources"] == 0
        assert result["bookSources"] == []
        assert result["rssSources"] == []


class TestSourceAppServiceEventPublishing:
    """测试领域事件发布（通过 mock event_bus 验证）"""

    @pytest.mark.asyncio
    async def test_create_book_source_发布SourceCreatedEvent(self, source_service):
        # mock event_bus.publish
        with patch("app.application.services.source_service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()

            await source_service.create_book_source({
                "bookSourceUrl": "https://example.com",
                "bookSourceName": "测试",
            })

            # 验证事件被发布
            mock_bus.publish.assert_called_once()
            event = mock_bus.publish.call_args[0][0]
            assert event.source_url == "https://example.com"
            assert event.source_name == "测试"
            assert event.source_type == "book"

    @pytest.mark.asyncio
    async def test_update_book_source_有变更时发布事件(self, source_service):
        await source_service.create_book_source({
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "原名",
        })

        with patch("app.application.services.source_service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()

            await source_service.update_book_source(
                "https://example.com", {"bookSourceName": "新名"}
            )

            mock_bus.publish.assert_called_once()
            event = mock_bus.publish.call_args[0][0]
            assert "bookSourceName" in event.changed_fields

    @pytest.mark.asyncio
    async def test_update_book_source_无变更不发布事件(self, source_service):
        await source_service.create_book_source({
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "原名",
        })

        with patch("app.application.services.source_service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()

            # 更新为相同值
            await source_service.update_book_source(
                "https://example.com", {"bookSourceName": "原名"}
            )

            mock_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_book_source_发布SourceDeletedEvent(self, source_service):
        await source_service.create_book_source({
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "待删除",
        })

        with patch("app.application.services.source_service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()

            await source_service.delete_book_source("https://example.com")

            mock_bus.publish.assert_called_once()
            event = mock_bus.publish.call_args[0][0]
            assert event.source_url == "https://example.com"
            assert event.source_type == "book"


class TestSourceAppServiceRssAndSubscription:
    """测试订阅源和订阅管理"""

    @pytest.mark.asyncio
    async def test_create_and_get_rss_source(self, source_service):
        await source_service.create_rss_source({
            "sourceUrl": "https://rss.example.com",
            "sourceName": "RSS源",
        })
        result = await source_service.get_rss_source("https://rss.example.com")
        assert result is not None
        assert result.sourceName == "RSS源"

    @pytest.mark.asyncio
    async def test_get_rss_source_不存在抛出异常(self, source_service):
        with pytest.raises(NotFoundException, match="订阅源不存在"):
            await source_service.get_rss_source("https://not-exist.com")

    @pytest.mark.asyncio
    async def test_create_and_delete_subscription(self, source_service):
        sub = await source_service.create_subscription(
            name="测试订阅", url="https://sub.com", sub_type="book"
        )
        assert sub.id > 0
        assert sub.name == "测试订阅"

        # 列出订阅
        subs = await source_service.list_subscriptions()
        assert len(subs) >= 1

        # 删除订阅
        result = await source_service.delete_subscription(sub.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_subscription_不存在返回False(self, source_service):
        result = await source_service.delete_subscription(9999)
        assert result is False

    @pytest.mark.asyncio
    async def test_filter_rule_crud(self, source_service):
        rule = await source_service.create_filter_rule({
            "name": "广告过滤",
            "pattern": "广告",
            "scope": "sourceName",
        })
        assert rule.id > 0

        rules = await source_service.list_filter_rules(enabled_only=True)
        assert len(rules) >= 1

        result = await source_service.delete_filter_rule(rule.id)
        assert result is True

        rules = await source_service.list_filter_rules(enabled_only=True)
        assert len(rules) == 0
