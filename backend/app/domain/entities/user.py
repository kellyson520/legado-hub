"""
用户与认证领域实体
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime


@dataclass
class User:
    """用户实体"""
    id: int = 0
    username: str = ""
    email: Optional[str] = None
    password_hash: Optional[str] = None
    role: str = "user"  # admin, user, viewer
    group_id: Optional[int] = None
    is_active: bool = True
    createdAt: datetime = field(default_factory=datetime.utcnow)
    updatedAt: datetime = field(default_factory=datetime.utcnow)


@dataclass
class UserGroup:
    """用户组实体"""
    id: int = 0
    name: str = ""
    description: Optional[str] = None
    default_permissions: Optional[Dict[str, Any]] = None
    createdAt: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ApiKey:
    """API Key 实体"""
    id: int = 0
    key_hash: str = ""
    name: Optional[str] = None
    user_id: Optional[int] = None
    is_enabled: bool = True
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    permissions: Optional[Dict[str, Any]] = None
    # 配额
    daily_fetch_quota: int = 500
    daily_ai_quota: int = 100000
    max_storage_mb: int = 1024
    max_concurrent_tasks: int = 10
    createdAt: datetime = field(default_factory=datetime.utcnow)
    updatedAt: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AuditLog:
    """审计日志实体"""
    id: int = 0
    api_key_id: Optional[int] = None
    user_id: Optional[int] = None
    action: str = ""
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    createdAt: datetime = field(default_factory=datetime.utcnow)


@dataclass
class QuotaUsage:
    """配额使用实体"""
    id: int = 0
    api_key_id: int = 0
    date: str = ""  # YYYY-MM-DD
    fetch_count: int = 0
    ai_chars: int = 0
    storage_mb: float = 0.0
    createdAt: datetime = field(default_factory=datetime.utcnow)
    updatedAt: datetime = field(default_factory=datetime.utcnow)
