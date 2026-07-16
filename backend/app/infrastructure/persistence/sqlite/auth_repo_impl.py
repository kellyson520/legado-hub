from datetime import datetime

from sqlalchemy import or_

from app.core.pagination import LIKE_ESCAPE, like_pattern
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
            .join(UserRoleModel, UserRoleModel.role_id == RolePermissionModel.role_id)
            .filter(UserRoleModel.user_id == user_id)
            .distinct()
            .all()
        )
        return [row[0] for row in rows]

    def _user_from_model(self, db, model: UserModel) -> User:
        return User(
            id=model.id,
            username=model.username,
            display_name=model.display_name,
            password_hash=model.password_hash,
            is_active=model.is_active,
            created_at=model.created_at,
            last_login_at=model.last_login_at,
            role_names=self._role_names_for_user(db, model.id),
            permissions=self._permissions_for_user(db, model.id),
        )

    async def get_user_by_username(self, username: str) -> User | None:
        db = SessionLocal()
        try:
            model = db.query(UserModel).filter(UserModel.username == username).first()
            return self._user_from_model(db, model) if model else None
        finally:
            db.close()

    async def save_user(self, user: User) -> User:
        db = SessionLocal()
        try:
            model = UserModel(
                username=user.username,
                display_name=user.display_name,
                password_hash=user.password_hash,
                is_active=user.is_active,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._user_from_model(db, model)
        finally:
            db.close()

    async def list_users(self) -> list[User]:
        db = SessionLocal()
        try:
            rows = db.query(UserModel).order_by(UserModel.id.asc()).all()
            return [self._user_from_model(db, row) for row in rows]
        finally:
            db.close()

    async def list_users_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
    ) -> tuple[list[User], int]:
        db = SessionLocal()
        try:
            query = db.query(UserModel)
            if status == "enabled":
                query = query.filter(UserModel.is_active == True)
            elif status == "disabled":
                query = query.filter(UserModel.is_active == False)
            normalized_search = search.strip()
            if normalized_search:
                pattern = like_pattern(normalized_search)
                query = query.filter(
                    or_(
                        UserModel.username.ilike(pattern, escape=LIKE_ESCAPE),
                        UserModel.display_name.ilike(pattern, escape=LIKE_ESCAPE),
                    )
                )
            total = query.count()
            rows = (
                query.order_by(UserModel.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return [self._user_from_model(db, row) for row in rows], total
        finally:
            db.close()

    async def get_user_by_id(self, user_id: int) -> User | None:
        db = SessionLocal()
        try:
            model = db.query(UserModel).filter(UserModel.id == user_id).first()
            return self._user_from_model(db, model) if model else None
        finally:
            db.close()

    async def update_user(
        self,
        user_id: int,
        *,
        display_name: str | None = None,
        password_hash: str | None = None,
        is_active: bool | None = None,
        role_names: list[str] | None = None,
        last_login_at: datetime | None = None,
    ) -> User | None:
        db = SessionLocal()
        try:
            model = db.query(UserModel).filter(UserModel.id == user_id).first()
            if model is None:
                return None
            if display_name is not None:
                model.display_name = display_name
            if password_hash is not None:
                model.password_hash = password_hash
            if is_active is not None:
                model.is_active = is_active
            if last_login_at is not None:
                model.last_login_at = last_login_at
            if role_names is not None:
                db.query(UserRoleModel).filter(UserRoleModel.user_id == user_id).delete()
                for role in db.query(RoleModel).filter(RoleModel.name.in_(role_names)).all():
                    db.add(UserRoleModel(user_id=user_id, role_id=role.id))
            db.commit()
            db.refresh(model)
            return self._user_from_model(db, model)
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
            db.query(RolePermissionModel).filter(RolePermissionModel.role_id == role.id).delete()
            if permissions:
                permission_rows = db.query(PermissionModel).filter(PermissionModel.name.in_(permissions)).all()
            else:
                permission_rows = []
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
        db = SessionLocal()
        try:
            model = db.query(RefreshTokenModel).filter(RefreshTokenModel.id == session_id).first()
            if model is not None:
                model.revoked_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()

    async def revoke_all_refresh_sessions(self, user_id: int) -> None:
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
            return ApiKey(
                id=model.id,
                name=model.name,
                key_hash=model.key_hash,
                permissions=api_key.permissions,
                is_enabled=model.is_enabled,
                created_at=model.created_at,
            )
        finally:
            db.close()

    async def get_api_key_by_hash(self, key_hash: str) -> ApiKey | None:
        db = SessionLocal()
        try:
            model = db.query(ApiKeyModel).filter(ApiKeyModel.key_hash == key_hash).first()
            if model is None:
                return None
            permission_rows = (
                db.query(ApiKeyPermissionModel.permission_name)
                .filter(ApiKeyPermissionModel.api_key_id == model.id)
                .all()
            )
            return ApiKey(
                id=model.id,
                name=model.name,
                key_hash=model.key_hash,
                permissions=sorted(row[0] for row in permission_rows),
                is_enabled=model.is_enabled,
                created_at=model.created_at,
            )
        finally:
            db.close()

    async def list_api_keys(self) -> list[ApiKey]:
        db = SessionLocal()
        try:
            result = []
            for model in db.query(ApiKeyModel).order_by(ApiKeyModel.id.asc()).all():
                permission_rows = (
                    db.query(ApiKeyPermissionModel.permission_name)
                    .filter(ApiKeyPermissionModel.api_key_id == model.id)
                    .all()
                )
                result.append(
                    ApiKey(
                        id=model.id,
                        name=model.name,
                        key_hash=model.key_hash,
                        permissions=[row[0] for row in permission_rows],
                        is_enabled=model.is_enabled,
                        created_at=model.created_at,
                    )
                )
            return result
        finally:
            db.close()

    async def list_api_keys_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
    ) -> tuple[list[ApiKey], int]:
        db = SessionLocal()
        try:
            query = db.query(ApiKeyModel)
            if status == "enabled":
                query = query.filter(ApiKeyModel.is_enabled == True)
            elif status == "disabled":
                query = query.filter(ApiKeyModel.is_enabled == False)
            normalized_search = search.strip()
            if normalized_search:
                query = query.filter(ApiKeyModel.name.ilike(like_pattern(normalized_search), escape=LIKE_ESCAPE))
            total = query.count()
            models = (
                query.order_by(ApiKeyModel.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            result = []
            for model in models:
                permission_rows = (
                    db.query(ApiKeyPermissionModel.permission_name)
                    .filter(ApiKeyPermissionModel.api_key_id == model.id)
                    .all()
                )
                result.append(
                    ApiKey(
                        id=model.id,
                        name=model.name,
                        key_hash=model.key_hash,
                        permissions=[row[0] for row in permission_rows],
                        is_enabled=model.is_enabled,
                        created_at=model.created_at,
                    )
                )
            return result, total
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
            result = []
            for role in db.query(RoleModel).order_by(RoleModel.id.asc()).all():
                permission_rows = (
                    db.query(PermissionModel.name)
                    .join(RolePermissionModel, RolePermissionModel.permission_id == PermissionModel.id)
                    .filter(RolePermissionModel.role_id == role.id)
                    .all()
                )
                result.append(
                    Role(
                        id=role.id,
                        name=role.name,
                        description=role.description,
                        permissions=[row[0] for row in permission_rows],
                    )
                )
            return result
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
            return AuditEvent(
                id=model.id,
                actor_id=model.actor_id,
                action=model.action,
                resource=model.resource,
                detail=model.detail,
                created_at=model.created_at,
            )
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

    async def list_audit_events_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        search: str = "",
    ) -> tuple[list[AuditEvent], int]:
        db = SessionLocal()
        try:
            query = db.query(AuditLogModel)
            normalized_search = search.strip()
            if normalized_search:
                pattern = like_pattern(normalized_search)
                query = query.filter(
                    or_(
                        AuditLogModel.action.ilike(pattern, escape=LIKE_ESCAPE),
                        AuditLogModel.resource.ilike(pattern, escape=LIKE_ESCAPE),
                        AuditLogModel.detail.ilike(pattern, escape=LIKE_ESCAPE),
                    )
                )
            total = query.count()
            rows = (
                query.order_by(AuditLogModel.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
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
            ], total
        finally:
            db.close()
