"""SQLite 用户管理仓储实现"""

from typing import List, Optional

from ....domain.repositories.user_repo import UserRepository
from ....domain.entities.user import User, ApiKey, AuditLog, QuotaUsage
from ....database import SessionLocal, UserModel, ApiKeyModel, AuditLogModel, QuotaUsageModel
from ....core.logging import get_logger

logger = get_logger("repo.user")


class SQLiteUserRepository(UserRepository):
    """SQLite 用户管理仓储实现"""
    
    def _to_entity_user(self, model: UserModel) -> User:
        return User(
            id=model.id, username=model.username, email=model.email,
            password_hash=model.password_hash, role=model.role,
            group_id=model.group_id, is_active=model.is_active,
            createdAt=model.createdAt, updatedAt=model.updatedAt,
        )
    
    def _to_entity_key(self, model: ApiKeyModel) -> ApiKey:
        return ApiKey(
            id=model.id, key_hash=model.key_hash, name=model.name,
            user_id=model.user_id, is_enabled=model.is_enabled,
            expires_at=model.expires_at, last_used_at=model.last_used_at,
            permissions=model.permissions,
            daily_fetch_quota=model.daily_fetch_quota,
            daily_ai_quota=model.daily_ai_quota,
            max_storage_mb=model.max_storage_mb,
            max_concurrent_tasks=model.max_concurrent_tasks,
            createdAt=model.createdAt, updatedAt=model.updatedAt,
        )
    
    def _to_entity_log(self, model: AuditLogModel) -> AuditLog:
        return AuditLog(
            id=model.id, api_key_id=model.api_key_id, user_id=model.user_id,
            action=model.action, resource_type=model.resource_type,
            resource_id=model.resource_id, details=model.details,
            ip_address=model.ip_address, createdAt=model.createdAt,
        )
    
    def _to_entity_quota(self, model: QuotaUsageModel) -> QuotaUsage:
        return QuotaUsage(
            id=model.id, api_key_id=model.api_key_id, date=model.date,
            fetch_count=model.fetch_count or 0, ai_chars=model.ai_chars or 0,
            storage_mb=model.storage_mb or 0.0,
            createdAt=model.createdAt, updatedAt=model.updatedAt,
        )
    
    # ==================== User ====================
    
    async def get_user(self, user_id: int) -> Optional[User]:
        db = SessionLocal()
        try:
            model = db.query(UserModel).filter(UserModel.id == user_id).first()
            return self._to_entity_user(model) if model else None
        finally:
            db.close()
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        db = SessionLocal()
        try:
            model = db.query(UserModel).filter(UserModel.username == username).first()
            return self._to_entity_user(model) if model else None
        finally:
            db.close()
    
    async def list_users(self, page=1, page_size=50):
        db = SessionLocal()
        try:
            query = db.query(UserModel)
            total = query.count()
            models = query.offset((page - 1) * page_size).limit(page_size).all()
            return [self._to_entity_user(m) for m in models], total
        finally:
            db.close()
    
    async def save_user(self, user: User) -> User:
        db = SessionLocal()
        try:
            if user.id:
                model = db.query(UserModel).filter(UserModel.id == user.id).first()
                if model:
                    model.username = user.username
                    model.email = user.email
                    model.password_hash = user.password_hash
                    model.role = user.role
                    model.group_id = user.group_id
                    model.is_active = user.is_active
                else:
                    model = UserModel(**user.__dict__)
                    db.add(model)
            else:
                model = UserModel(**user.__dict__)
                db.add(model)
            db.commit()
            db.refresh(model)
            user.id = model.id
            return user
        finally:
            db.close()
    
    async def delete_user(self, user_id: int) -> bool:
        db = SessionLocal()
        try:
            model = db.query(UserModel).filter(UserModel.id == user_id).first()
            if model:
                db.delete(model)
                db.commit()
                return True
            return False
        finally:
            db.close()
    
    # ==================== ApiKey ====================
    
    async def get_api_key_by_hash(self, key_hash: str) -> Optional[ApiKey]:
        db = SessionLocal()
        try:
            model = db.query(ApiKeyModel).filter(ApiKeyModel.key_hash == key_hash).first()
            return self._to_entity_key(model) if model else None
        finally:
            db.close()
    
    async def get_api_key(self, key_id: int) -> Optional[ApiKey]:
        db = SessionLocal()
        try:
            model = db.query(ApiKeyModel).filter(ApiKeyModel.id == key_id).first()
            return self._to_entity_key(model) if model else None
        finally:
            db.close()
    
    async def list_api_keys(self, user_id=None) -> List[ApiKey]:
        db = SessionLocal()
        try:
            query = db.query(ApiKeyModel)
            if user_id:
                query = query.filter(ApiKeyModel.user_id == user_id)
            models = query.all()
            return [self._to_entity_key(m) for m in models]
        finally:
            db.close()
    
    async def save_api_key(self, key: ApiKey) -> ApiKey:
        db = SessionLocal()
        try:
            if key.id:
                model = db.query(ApiKeyModel).filter(ApiKeyModel.id == key.id).first()
                if model:
                    model.name = key.name
                    model.is_enabled = key.is_enabled
                    model.permissions = key.permissions
                    model.daily_fetch_quota = key.daily_fetch_quota
                    model.daily_ai_quota = key.daily_ai_quota
                else:
                    model = ApiKeyModel(**key.__dict__)
                    db.add(model)
            else:
                model = ApiKeyModel(**key.__dict__)
                db.add(model)
            db.commit()
            db.refresh(model)
            key.id = model.id
            return key
        finally:
            db.close()
    
    async def delete_api_key(self, key_id: int) -> bool:
        db = SessionLocal()
        try:
            model = db.query(ApiKeyModel).filter(ApiKeyModel.id == key_id).first()
            if model:
                db.delete(model)
                db.commit()
                return True
            return False
        finally:
            db.close()
    
    async def update_api_key_last_used(self, key_id: int) -> bool:
        from datetime import datetime
        db = SessionLocal()
        try:
            model = db.query(ApiKeyModel).filter(ApiKeyModel.id == key_id).first()
            if model:
                model.last_used_at = datetime.utcnow()
                db.commit()
                return True
            return False
        finally:
            db.close()
    
    # ==================== AuditLog ====================
    
    async def list_audit_logs(self, action=None, api_key_id=None, page=1, page_size=50):
        db = SessionLocal()
        try:
            query = db.query(AuditLogModel).order_by(AuditLogModel.createdAt.desc())
            if action:
                query = query.filter(AuditLogModel.action == action)
            if api_key_id:
                query = query.filter(AuditLogModel.api_key_id == api_key_id)
            total = query.count()
            models = query.offset((page - 1) * page_size).limit(page_size).all()
            return [self._to_entity_log(m) for m in models], total
        finally:
            db.close()
    
    async def save_audit_log(self, log: AuditLog) -> AuditLog:
        db = SessionLocal()
        try:
            model = AuditLogModel(**log.__dict__)
            db.add(model)
            db.commit()
            db.refresh(model)
            log.id = model.id
            return log
        finally:
            db.close()
    
    async def delete_old_audit_logs(self, days=90) -> int:
        from datetime import datetime, timedelta
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            count = db.query(AuditLogModel).filter(AuditLogModel.createdAt < cutoff).delete(synchronize_session=False)
            db.commit()
            return count
        finally:
            db.close()
    
    # ==================== QuotaUsage ====================
    
    async def get_quota_usage(self, api_key_id: int, date: str) -> Optional[QuotaUsage]:
        db = SessionLocal()
        try:
            model = db.query(QuotaUsageModel).filter(
                QuotaUsageModel.api_key_id == api_key_id,
                QuotaUsageModel.date == date
            ).first()
            return self._to_entity_quota(model) if model else None
        finally:
            db.close()
    
    async def save_quota_usage(self, usage: QuotaUsage) -> QuotaUsage:
        db = SessionLocal()
        try:
            if usage.id:
                model = db.query(QuotaUsageModel).filter(QuotaUsageModel.id == usage.id).first()
                if model:
                    model.fetch_count = usage.fetch_count
                    model.ai_chars = usage.ai_chars
                    model.storage_mb = usage.storage_mb
                else:
                    model = QuotaUsageModel(**usage.__dict__)
                    db.add(model)
            else:
                model = QuotaUsageModel(**usage.__dict__)
                db.add(model)
            db.commit()
            db.refresh(model)
            usage.id = model.id
            return usage
        finally:
            db.close()
