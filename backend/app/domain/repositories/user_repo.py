"""
用户与认证仓储接口（抽象）
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from ..entities.user import User, UserGroup, ApiKey, AuditLog, QuotaUsage


class UserRepository(ABC):
    """用户管理仓储接口"""
    
    # ==================== User ====================
    
    @abstractmethod
    async def get_user(self, user_id: int) -> Optional[User]:
        pass
    
    @abstractmethod
    async def get_user_by_username(self, username: str) -> Optional[User]:
        pass
    
    @abstractmethod
    async def list_users(self, page: int = 1, page_size: int = 50) -> tuple[List[User], int]:
        pass
    
    @abstractmethod
    async def save_user(self, user: User) -> User:
        pass
    
    @abstractmethod
    async def delete_user(self, user_id: int) -> bool:
        pass
    
    # ==================== ApiKey ====================
    
    @abstractmethod
    async def get_api_key_by_hash(self, key_hash: str) -> Optional[ApiKey]:
        pass
    
    @abstractmethod
    async def get_api_key(self, key_id: int) -> Optional[ApiKey]:
        """通过 ID 获取 API Key"""
        pass
    
    @abstractmethod
    async def list_api_keys(self, user_id: Optional[int] = None) -> List[ApiKey]:
        pass
    
    @abstractmethod
    async def save_api_key(self, key: ApiKey) -> ApiKey:
        pass
    
    @abstractmethod
    async def delete_api_key(self, key_id: int) -> bool:
        pass
    
    @abstractmethod
    async def update_api_key_last_used(self, key_id: int) -> bool:
        pass
    
    # ==================== AuditLog ====================
    
    @abstractmethod
    async def list_audit_logs(
        self,
        action: Optional[str] = None,
        api_key_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 50
    ) -> tuple[List[AuditLog], int]:
        pass
    
    @abstractmethod
    async def save_audit_log(self, log: AuditLog) -> AuditLog:
        pass
    
    @abstractmethod
    async def delete_old_audit_logs(self, days: int = 90) -> int:
        """删除 N 天前的日志，返回删除数量"""
        pass
    
    # ==================== QuotaUsage ====================
    
    @abstractmethod
    async def get_quota_usage(self, api_key_id: int, date: str) -> Optional[QuotaUsage]:
        pass
    
    @abstractmethod
    async def save_quota_usage(self, usage: QuotaUsage) -> QuotaUsage:
        pass
