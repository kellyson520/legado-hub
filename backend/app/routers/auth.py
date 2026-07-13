from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from ..database import get_db, UserModel, UserGroupModel, ApiKeyModel, AuditLogModel, QuotaUsageModel
from ..models import ApiResponse, PaginatedResponse
from ..core.security import generate_api_key, hash_api_key, mask_api_key, create_access_token, verify_api_key
from ..core.dependencies import get_auth_context, require_admin, AuthContext

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ==================== Admin Auth ====================

@router.post("/login", response_model=ApiResponse)
async def admin_login(
    username: str,
    password: str,
    db: Session = Depends(get_db)
):
    """管理员登录，返回 JWT Token"""
    user = db.query(UserModel).filter(
        UserModel.username == username,
        UserModel.role == "admin"
    ).first()
    
    if not user or not pwd_context.verify(password, user.password_hash or ""):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": user.id}, expires_delta=timedelta(hours=24))
    return ApiResponse(data={"token": token, "user": {"id": user.id, "username": user.username, "role": user.role}})


@router.post("/setup", response_model=ApiResponse)
async def setup_admin(
    username: str,
    password: str,
    db: Session = Depends(get_db)
):
    """初始化管理员账号（仅当无管理员时可用）"""
    existing = db.query(UserModel).filter(UserModel.role == "admin").first()
    if existing:
        raise HTTPException(status_code=400, detail="Admin already exists")
    
    user = UserModel(
        username=username,
        password_hash=pwd_context.hash(password),
        role="admin",
        is_active=True
    )
    db.add(user)
    db.commit()
    return ApiResponse(message="Admin created")


# ==================== API Key Management ====================

@router.get("/keys", response_model=PaginatedResponse)
async def list_api_keys(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    """管理员：列出所有 API Key"""
    total = db.query(ApiKeyModel).count()
    items = db.query(ApiKeyModel).order_by(ApiKeyModel.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = []
    for item in items:
        d = {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
        d["key_masked"] = mask_api_key(item.key_hash[:8])  # 脱敏
        data.append(d)
    return PaginatedResponse(data=data, total=total, page=page, pageSize=page_size)


@router.post("/keys", response_model=ApiResponse)
async def create_api_key(
    name: Optional[str] = None,
    user_id: Optional[int] = None,
    expires_days: Optional[int] = None,
    permissions: Optional[dict] = None,
    daily_fetch_quota: int = 500,
    daily_ai_quota: int = 100000,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    """管理员：创建新 API Key"""
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    
    key = ApiKeyModel(
        key_hash=key_hash,
        name=name or "API Key",
        user_id=user_id,
        permissions=permissions,
        expires_at=datetime.utcnow() + timedelta(days=expires_days) if expires_days else None,
        daily_fetch_quota=daily_fetch_quota,
        daily_ai_quota=daily_ai_quota
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    
    return ApiResponse(data={
        "api_key": raw_key,  # 仅创建时返回一次
        "id": key.id,
        "name": key.name
    }, message="API Key created. Save it now - it won't be shown again.")


@router.put("/keys/{key_id}/status", response_model=ApiResponse)
async def toggle_api_key(
    key_id: int,
    is_enabled: bool,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    """启用/禁用 API Key"""
    key = db.query(ApiKeyModel).filter(ApiKeyModel.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    key.is_enabled = is_enabled
    db.commit()
    return ApiResponse(message=f"Key {'enabled' if is_enabled else 'disabled'}")


@router.delete("/keys/{key_id}", response_model=ApiResponse)
async def delete_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    """删除 API Key"""
    key = db.query(ApiKeyModel).filter(ApiKeyModel.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    db.delete(key)
    db.commit()
    return ApiResponse(message="Key deleted")


# ==================== Quota ====================

@router.get("/quota", response_model=ApiResponse)
async def get_quota(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context)
):
    """查询当前密钥的配额使用情况（Redis 优先，实时性更高）"""
    api_key = auth.api_key
    if not api_key:
        return ApiResponse(data={"unlimited": True})
    
    # 优先从 Redis 获取实时数据
    from ..core.redis_client import redis_client
    fetch_used = await redis_client.get_quota(api_key.id, "fetch_count")
    ai_used = await redis_client.get_quota(api_key.id, "ai_chars")
    storage_used = await redis_client.get_quota(api_key.id, "storage_mb")
    
    # Redis 无数据时回退到数据库
    if fetch_used == 0 and ai_used == 0 and storage_used == 0:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        usage = db.query(QuotaUsageModel).filter(
            QuotaUsageModel.api_key_id == api_key.id,
            QuotaUsageModel.date == today
        ).first()
        if usage:
            fetch_used = usage.fetch_count or 0
            ai_used = usage.ai_chars or 0
            storage_used = usage.storage_mb or 0.0
    
    return ApiResponse(data={
        "fetch": {
            "used": fetch_used,
            "total": api_key.daily_fetch_quota,
            "remaining": max(0, api_key.daily_fetch_quota - fetch_used)
        },
        "ai": {
            "used": ai_used,
            "total": api_key.daily_ai_quota,
            "remaining": max(0, api_key.daily_ai_quota - ai_used)
        },
        "storage_mb": {
            "used": float(storage_used or 0.0),
            "total": api_key.max_storage_mb
        },
        "concurrent": {
            "max": api_key.max_concurrent_tasks
        }
    })


@router.get("/verify", response_model=ApiResponse)
async def verify_token(
    auth: AuthContext = Depends(get_auth_context)
):
    """验证当前 API Key 有效性"""
    return ApiResponse(data={
        "valid": True,
        "is_admin": auth.is_admin,
        "permissions": {
            "source_read": auth.can_read_source,
            "source_import": auth.can_import_source,
            "source_edit": auth.can_edit_source,
            "source_publish": auth.can_publish_source,
            "ai_character": auth.can_use_ai_character,
            "ai_world": auth.can_use_ai_world,
            "ai_storyline": auth.can_use_ai_storyline,
            "ai_chat": auth.can_use_ai_chat,
            "ai_fix": auth.can_use_ai_fix,
            "view_sensitive": auth.can_view_sensitive,
            "export": auth.can_export
        }
    })


# ==================== Users & Groups ====================

@router.get("/users", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    total = db.query(UserModel).count()
    items = db.query(UserModel).order_by(UserModel.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        data=[{k: v for k, v in item.__dict__.items() if not k.startswith("_")} for item in items],
        total=total, page=page, pageSize=page_size
    )


@router.post("/users", response_model=ApiResponse)
async def create_user(
    username: str,
    password: str,
    role: str = "user",
    group_id: Optional[int] = None,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    existing = db.query(UserModel).filter(UserModel.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username exists")
    
    user = UserModel(
        username=username,
        password_hash=pwd_context.hash(password),
        role=role,
        group_id=group_id,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return ApiResponse(data={"id": user.id}, message="User created")


@router.get("/groups", response_model=ApiResponse)
async def list_groups(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    items = db.query(UserGroupModel).all()
    return ApiResponse(data=[{k: v for k, v in item.__dict__.items() if not k.startswith("_")} for item in items])


@router.post("/groups", response_model=ApiResponse)
async def create_group(
    name: str,
    description: Optional[str] = None,
    default_permissions: Optional[dict] = None,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    group = UserGroupModel(name=name, description=description, default_permissions=default_permissions)
    db.add(group)
    db.commit()
    db.refresh(group)
    return ApiResponse(data={"id": group.id}, message="Group created")


# ==================== Audit Logs ====================

@router.get("/audit", response_model=PaginatedResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    api_key_id: Optional[int] = None,
    action: Optional[str] = None,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    query = db.query(AuditLogModel)
    if api_key_id:
        query = query.filter(AuditLogModel.api_key_id == api_key_id)
    if action:
        query = query.filter(AuditLogModel.action == action)
    
    total = query.count()
    items = query.order_by(AuditLogModel.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        data=[{k: v for k, v in item.__dict__.items() if not k.startswith("_")} for item in items],
        total=total, page=page, pageSize=page_size
    )
