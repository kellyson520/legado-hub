"""
认证依赖注入 — 核心认证基础设施

职责：
- 提取并校验 API Key / JWT Token
- 构建认证上下文（AuthContext）
- 统一异常（AuthenticationException / AuthorizationException）
- 全链路日志（认证成功/失败/过期/禁用 全覆盖）
- 配额检查与同步（基于 Redis + DB 持久化）
- 通过仓储接口访问数据（DDD 解耦）

关键约束（禁止缺失日志）：
- 每个认证决策点（成功/失败/过期/禁用）必须有日志
- 权限校验结果必须有日志
- 配额检查必须有日志
- 日志携带 trace_id / user_id / api_key_id 上下文
"""

import time
from typing import Optional
from datetime import datetime
from fastapi import Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .logging import get_logger, set_log_context, clear_log_context
from .exceptions import AuthenticationException, AuthorizationException, QuotaExceededException
from .security import hash_api_key, decode_access_token, mask_api_key
from .config import settings
from .redis_client import redis_client
from .events import publish_event, AuditEvent

logger = get_logger("auth.dependencies")

security_bearer = HTTPBearer(auto_error=False)


# ==================== 配额管理 ====================

async def check_quota_redis(api_key_id: int, metric: str, limit: int, amount: int = 1) -> tuple[bool, int]:
    """
    基于 Redis 的配额检查
    Returns: (allowed, current_usage)
    """
    current = await redis_client.get_quota(api_key_id, metric)
    logger.debug(
        f"[Quota] 配额检查: key_id={api_key_id}, metric={metric}, current={current}, limit={limit}",
        extra={"action": "quota_check", "api_key_id": api_key_id, "metric": metric, "current": current, "limit": limit}
    )

    if current >= limit:
        logger.warning(
            f"[Quota] 配额超限: key_id={api_key_id}, metric={metric}, current={current}/{limit}",
            extra={"action": "quota_exceeded", "api_key_id": api_key_id, "metric": metric, "current": current, "limit": limit}
        )
        return False, current

    new_val = await redis_client.increment_quota(api_key_id, metric, amount)
    logger.debug(
        f"[Quota] 配额递增: key_id={api_key_id}, metric={metric}, new={new_val}",
        extra={"action": "quota_increment", "api_key_id": api_key_id, "metric": metric, "new_value": new_val}
    )
    return True, new_val


async def sync_quota_to_db(api_key_id: int):
    """将 Redis 配额计数同步到数据库（使用仓储接口）"""
    from ..infrastructure.persistence.factory import get_user_repo
    from ..domain.entities.user import QuotaUsage

    start = time.time()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    logger.debug(
        f"[Quota] 开始同步配额到 DB: key_id={api_key_id}",
        extra={"action": "quota_sync_start", "api_key_id": api_key_id}
    )

    try:
        repo = get_user_repo()
        fetch_count = await redis_client.get_quota(api_key_id, "fetch_count")
        ai_chars = await redis_client.get_quota(api_key_id, "ai_chars")

        existing = await repo.get_quota_usage(api_key_id, today)

        if not existing:
            usage = QuotaUsage(
                api_key_id=api_key_id, date=today,
                fetch_count=fetch_count, ai_chars=ai_chars
            )
            await repo.save_quota_usage(usage)
        else:
            existing.fetch_count = max(existing.fetch_count or 0, fetch_count)
            existing.ai_chars = max(existing.ai_chars or 0, ai_chars)
            await repo.save_quota_usage(existing)

        elapsed = (time.time() - start) * 1000
        logger.info(
            f"[Quota] 配额同步完成: key_id={api_key_id}, fetch={fetch_count}, ai_chars={ai_chars}, elapsed={elapsed:.0f}ms",
            extra={
                "action": "quota_sync_done", "api_key_id": api_key_id,
                "fetch_count": fetch_count, "ai_chars": ai_chars, "duration_ms": round(elapsed, 2)
            }
        )
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        logger.error(
            f"[Quota] 配额同步失败: key_id={api_key_id} - {type(e).__name__}: {e}",
            extra={"action": "quota_sync_error", "api_key_id": api_key_id, "error": str(e), "duration_ms": round(elapsed, 2)},
            exc_info=True
        )


# ==================== 认证上下文 ====================

# 默认权限模板
_DEFAULT_PERMISSIONS = {
    "source_read": True,
    "source_import": True,
    "source_edit": True,
    "source_publish": True,
    "ai_character": True,
    "ai_world": True,
    "ai_storyline": True,
    "ai_chat": True,
    "ai_fix": True,
    "view_sensitive": True,
    "export": True,
}

_PERMISSION_KEYS = list(_DEFAULT_PERMISSIONS.keys())


class AuthContext:
    """
    认证上下文 — 携带密钥信息和用户权限

    设计：
    - 不直接暴露 ORM 模型，仅暴露权限标记
    - api_key_id / user_id 供日志追踪使用
    - 所有权限检查通过 has_permission() 统一入口
    """

    def __init__(
        self,
        api_key_id: Optional[int] = None,
        api_key_name: Optional[str] = None,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        permissions: Optional[dict] = None,
    ):
        self.api_key_id = api_key_id
        self.api_key_name = api_key_name
        self.user_id = user_id
        self.username = username
        self.is_admin = False
        self.permissions = permissions or {}

        # 设置权限标记（供外部快速检查）
        for key in _PERMISSION_KEYS:
            setattr(self, f"can_{key}", self.permissions.get(key, True))

    @classmethod
    def from_api_key(cls, key_entity) -> "AuthContext":
        """从 ApiKey 领域实体构建"""
        is_admin = False
        user_id = key_entity.user_id
        username = None
        if user_id:
            # 延迟查询用户信息
            pass

        ctx = cls(
            api_key_id=key_entity.id,
            api_key_name=key_entity.name,
            user_id=user_id,
            username=username,
            permissions=key_entity.permissions or {},
        )
        return ctx

    @classmethod
    def from_user(cls, user_entity) -> "AuthContext":
        """从 User 领域实体构建（JWT 登录）"""
        ctx = cls(
            user_id=user_entity.id,
            username=user_entity.username,
        )
        ctx.is_admin = (user_entity.role == "admin")
        # 管理员拥有所有权限
        if ctx.is_admin:
            ctx.permissions = {k: True for k in _PERMISSION_KEYS}
            for key in _PERMISSION_KEYS:
                setattr(ctx, f"can_{key}", True)
        return ctx

    def has_permission(self, permission: str) -> bool:
        """统一权限检查入口"""
        if self.is_admin:
            return True
        return self.permissions.get(permission, True)


# ==================== 认证提取 ====================

async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Security(security_bearer),
) -> AuthContext:
    """
    提取并校验凭证，构建认证上下文。

    支持两种认证方式：
    1. Bearer lh_xxx — API Key 认证（通过仓储接口查询）
    2. Bearer eyJxxx — JWT Token 认证（管理员登录）

    日志覆盖：
    - 缺失 Header → AuthenticationException + WARNING
    - API Key 无效/禁用 → AuthenticationException + WARNING
    - API Key 过期 → AuthenticationException + WARNING
    - JWT 无效 → AuthenticationException + WARNING
    - 认证成功 → INFO + 上下文注入
    """
    if not credentials:
        logger.warning(
            "[Auth] 缺少 Authorization 头",
            extra={"action": "auth_missing_header"}
        )
        raise AuthenticationException("Missing Authorization header")

    token = credentials.credentials
    token_type = "api_key" if token.startswith("lh_") else "jwt"

    try:
        if token.startswith("lh_"):
            ctx = await _authenticate_api_key(token)
        else:
            ctx = await _authenticate_jwt(token)

        # 注入日志上下文（后续请求链路中所有日志都会携带）
        set_log_context(
            api_key_id=ctx.api_key_id,
            user_id=str(ctx.user_id) if ctx.user_id else None,
        )

        logger.info(
            f"[Auth] 认证成功: type={token_type}, key_id={ctx.api_key_id}, user_id={ctx.user_id}, admin={ctx.is_admin}",
            extra={
                "action": "auth_success",
                "auth_type": token_type,
                "api_key_id": ctx.api_key_id,
                "user_id": ctx.user_id,
                "is_admin": ctx.is_admin,
            }
        )

        return ctx

    except AuthenticationException:
        # AuthenticationException 已在子函数中记录日志，直接抛出
        raise
    except Exception as e:
        logger.error(
            f"[Auth] 认证异常: {type(e).__name__}: {e}",
            extra={"action": "auth_error", "auth_type": token_type, "error": str(e)},
            exc_info=True
        )
        raise AuthenticationException("认证过程发生异常")


async def _authenticate_api_key(token: str) -> AuthContext:
    """API Key 认证路径"""
    from ..infrastructure.persistence.factory import get_user_repo

    hashed = hash_api_key(token)
    masked = mask_api_key(token)

    logger.debug(
        f"[Auth] API Key 认证: masked={masked}",
        extra={"action": "auth_api_key_start", "masked_key": masked}
    )

    # 通过仓储接口查询（DDD 解耦，不直接操作 ORM）
    repo = get_user_repo()
    key_entity = await repo.get_api_key_by_hash(hashed)

    if not key_entity:
        logger.warning(
            f"[Auth] API Key 无效或已禁用: masked={masked}",
            extra={"action": "auth_api_key_invalid", "masked_key": masked}
        )
        raise AuthenticationException("Invalid or disabled API key")

    if not key_entity.is_enabled:
        logger.warning(
            f"[Auth] API Key 已禁用: id={key_entity.id}, name={key_entity.name}",
            extra={"action": "auth_api_key_disabled", "api_key_id": key_entity.id, "key_name": key_entity.name}
        )
        raise AuthenticationException("API key is disabled")

    if key_entity.expires_at and key_entity.expires_at < datetime.utcnow():
        logger.warning(
            f"[Auth] API Key 已过期: id={key_entity.id}, expired_at={key_entity.expires_at.isoformat()}",
            extra={"action": "auth_api_key_expired", "api_key_id": key_entity.id, "expired_at": key_entity.expires_at.isoformat()}
        )
        raise AuthenticationException("API key expired")

    # 更新最后使用时间（异步，不阻塞认证）
    try:
        await repo.update_api_key_last_used(key_entity.id)
    except Exception as e:
        logger.error(
            f"[Auth] 更新 API Key 使用时间失败: id={key_entity.id} - {e}",
            extra={"action": "auth_update_last_used_error", "api_key_id": key_entity.id, "error": str(e)},
            exc_info=True
        )
        # 非关键操作，不阻断认证流程

    # 查询关联用户
    user = None
    if key_entity.user_id:
        try:
            user = await repo.get_user(key_entity.user_id)
        except Exception as e:
            logger.error(
                f"[Auth] 查询关联用户失败: key_id={key_entity.id}, user_id={key_entity.user_id} - {e}",
                extra={"action": "auth_load_user_error", "api_key_id": key_entity.id, "user_id": key_entity.user_id, "error": str(e)},
                exc_info=True
            )

    ctx = AuthContext.from_api_key(key_entity)

    if user:
        ctx.user_id = user.id
        ctx.username = user.username
        ctx.is_admin = (user.role == "admin")
        if ctx.is_admin:
            ctx.permissions = {k: True for k in _PERMISSION_KEYS}
            for key in _PERMISSION_KEYS:
                setattr(ctx, f"can_{key}", True)

    return ctx


async def _authenticate_jwt(token: str) -> AuthContext:
    """JWT Token 认证路径（管理员登录）"""
    from ..infrastructure.persistence.factory import get_user_repo

    logger.debug(
        "[Auth] JWT Token 认证",
        extra={"action": "auth_jwt_start"}
    )

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        logger.warning(
            "[Auth] JWT 解析失败或缺少 sub",
            extra={"action": "auth_jwt_invalid"}
        )
        raise AuthenticationException("Invalid JWT token")

    try:
        user_id = int(payload.get("sub"))
    except (ValueError, TypeError):
        logger.warning(
            f"[Auth] JWT sub 非法: sub={payload.get('sub')}",
            extra={"action": "auth_jwt_bad_sub", "sub": payload.get("sub")}
        )
        raise AuthenticationException("Invalid JWT token")

    repo = get_user_repo()
    user = await repo.get_user(user_id)

    if not user or not user.is_active:
        logger.warning(
            f"[Auth] JWT 用户不存在或已禁用: user_id={user_id}",
            extra={"action": "auth_jwt_user_not_found", "user_id": user_id}
        )
        raise AuthenticationException("User not found or disabled")

    return AuthContext.from_user(user)


# ==================== 权限守卫 ====================

async def require_admin(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """要求管理员权限 — 统一日志 + 统一异常"""
    if not auth.is_admin:
        logger.warning(
            f"[Auth] 管理员权限校验失败: user_id={auth.user_id}, key_id={auth.api_key_id}",
            extra={
                "action": "permission_denied",
                "required": "admin",
                "user_id": auth.user_id,
                "api_key_id": auth.api_key_id,
            }
        )
        raise AuthorizationException("Admin permission required")
    return auth


def require_permission(permission: str):
    """
    要求特定权限的装饰器工厂

    日志覆盖：
    - 管理员跳过检查 → DEBUG
    - 权限通过 → DEBUG
    - 权限拒绝 → WARNING + AuthorizationException
    """
    async def checker(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if auth.is_admin:
            logger.debug(
                f"[Auth] 管理员跳过权限检查: permission={permission}",
                extra={"action": "permission_admin_bypass", "permission": permission}
            )
            return auth

        if not auth.has_permission(permission):
            logger.warning(
                f"[Auth] 权限不足: permission={permission}, key_id={auth.api_key_id}, user_id={auth.user_id}",
                extra={
                    "action": "permission_denied",
                    "required": permission,
                    "user_id": auth.user_id,
                    "api_key_id": auth.api_key_id,
                }
            )
            raise AuthorizationException(f"Permission denied: {permission}")

        logger.debug(
            f"[Auth] 权限通过: permission={permission}",
            extra={"action": "permission_granted", "permission": permission}
        )
        return auth

    return checker
