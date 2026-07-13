"""
认证与授权接口层 (v1 - Pro API)

职责：
- 接收 HTTP 请求
- 调用 AuthAppService
- 返回统一格式响应
- 统一异常 + 统一日志
"""

from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query

from ....core.response import ok, paginated, fail
from ....core.logging import get_logger
from ....core.exceptions import ValidationException
from ....core.dependencies import get_auth_context, require_admin, AuthContext
from ....core.security import mask_api_key, verify_api_key
from ....application.services import AuthAppService
from ..dependencies import get_auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = get_logger("api.auth")


# ==================== Admin Auth ====================

@router.post("/login")
async def admin_login(
    username: str,
    password: str,
    svc: AuthAppService = Depends(get_auth_service)
):
    """管理员登录，返回 JWT Token"""
    if not username or not password:
        raise ValidationException("用户名和密码不能为空")

    logger.info(f"[Auth] 管理员登录尝试: username={username}", extra={"action": "admin_login", "username": username})

    token = await svc.login(username, password)
    user = await svc.get_user_by_username(username)
    return ok({
        "token": token,
        "user": {"id": user.id, "username": user.username, "role": user.role}
    })


@router.post("/setup")
async def setup_admin(
    username: str,
    password: str,
    svc: AuthAppService = Depends(get_auth_service)
):
    """初始化管理员账号"""
    if not username or not password:
        raise ValidationException("用户名和密码不能为空")

    logger.info(f"[Auth] 初始化管理员: username={username}", extra={"action": "admin_setup"})
    await svc.setup_admin(username, password)
    return ok(message="管理员创建成功")


# ==================== API Key Management ====================

@router.get("/keys")
async def list_api_keys(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: AuthAppService = Depends(get_auth_service),
    auth: AuthContext = Depends(require_admin)
):
    """管理员：列出所有 API Key"""
    logger.debug("[Auth] 列出 API Key", extra={"action": "list_keys"})
    items = await svc.list_api_keys()
    data = []
    for item in items:
        d = item.__dict__.copy()
        d["key_masked"] = mask_api_key(item.key_hash[:8])
        data.append(d)
    return paginated(data, len(data), page, page_size)


@router.post("/keys")
async def create_api_key(
    data: dict,
    svc: AuthAppService = Depends(get_auth_service),
    auth: AuthContext = Depends(require_admin)
):
    """创建 API Key"""
    name = data.get("name", "")
    permissions = data.get("permissions")
    logger.info(f"[Auth] 创建 API Key: name={name}", extra={"action": "create_key", "key_name": name})

    raw_key, key = await svc.create_api_key(name=name, permissions=permissions)
    return ok({
        "api_key": raw_key,
        "key_id": key.id,
        "name": key.name,
        "permissions": key.permissions
    }, "API Key 创建成功")


@router.delete("/keys/{key_id}")
async def delete_api_key(
    key_id: int,
    svc: AuthAppService = Depends(get_auth_service),
    auth: AuthContext = Depends(require_admin)
):
    """删除 API Key"""
    logger.info(f"[Auth] 删除 API Key: id={key_id}", extra={"action": "delete_key", "key_id": key_id})
    await svc.delete_api_key(key_id)
    return ok(message="API Key 删除成功")


# ==================== Quota ====================

@router.get("/quota")
async def get_quota(
    svc: AuthAppService = Depends(get_auth_service),
    auth: AuthContext = Depends(get_auth_context)
):
    """查询配额"""
    # JWT 登录用户无 API Key，返回无限配额
    if not auth.api_key_id:
        return ok({"unlimited": True})

    today = datetime.utcnow().strftime("%Y-%m-%d")
    usage = await svc.get_quota(auth.api_key_id, today)

    # 查询 API Key 配额配置
    from ....infrastructure.persistence.factory import get_user_repo
    repo = get_user_repo()
    key_entity = await repo.get_api_key(auth.api_key_id)

    default_fetch = key_entity.daily_fetch_quota if key_entity else 500
    default_ai = key_entity.daily_ai_quota if key_entity else 100000
    default_storage = key_entity.max_storage_mb if key_entity else 1024

    return ok({
        "fetch": {
            "used": usage.fetch_count if usage else 0,
            "total": default_fetch
        },
        "ai": {
            "used": usage.ai_chars if usage else 0,
            "total": default_ai
        },
        "storage_mb": {
            "used": usage.storage_mb if usage else 0.0,
            "total": default_storage
        }
    })


# ==================== Users ====================

@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: AuthAppService = Depends(get_auth_service),
    auth: AuthContext = Depends(require_admin)
):
    """列出用户"""
    logger.debug("[Auth] 列出用户", extra={"action": "list_users"})
    items, total = await svc.list_users(page, page_size)
    return paginated([item.__dict__ for item in items], total, page, page_size)


# ==================== Audit Logs ====================

@router.get("/audit")
async def list_audit_logs(
    action: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: AuthAppService = Depends(get_auth_service),
    auth: AuthContext = Depends(require_admin)
):
    """审计日志"""
    logger.debug("[Auth] 查询审计日志", extra={"action": "list_audit"})
    items, total = await svc.list_audit_logs(action=action, page=page, page_size=page_size)
    return paginated([item.__dict__ for item in items], total, page, page_size)


# ==================== Verify ====================

@router.get("/verify")
async def verify_token(auth: AuthContext = Depends(get_auth_context)):
    """验证 Token 并返回权限信息"""
    return ok({
        "valid": True,
        "is_admin": auth.is_admin,
        "permissions": auth.permissions,
        "api_key_id": auth.api_key_id,
        "user_id": auth.user_id,
        "username": auth.username,
    })
