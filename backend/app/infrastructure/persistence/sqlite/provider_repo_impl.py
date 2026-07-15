import json
from uuid import uuid4

from app.database import SessionLocal
from app.domain.entities.provider import ProviderAccount, ProviderModel, ProviderRoute, QuotaPolicy
from app.domain.repositories.provider_repo import ProviderRepository

from .schema import ProviderAccountModel, ProviderModelModel, ProviderRouteModel, QuotaPolicyModel


class SQLiteProviderRepository(ProviderRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    def create_provider_account(self, name: str, provider_type: str, base_url: str) -> ProviderAccount:
        db = self._db()
        try:
            model = ProviderAccountModel(
                id=uuid4().hex,
                name=name,
                provider_type=provider_type,
                base_url=base_url,
                enabled=True,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return ProviderAccount(
                id=model.id,
                name=model.name,
                provider_type=model.provider_type,
                base_url=model.base_url,
                api_key=model.api_key,
                default_model=model.default_model,
                enabled=model.enabled,
                created_at=model.created_at,
            )
        finally:
            self._close(db)

    def upsert_llm_provider(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
    ) -> ProviderAccount:
        existing = self.get_provider_by_name(name)
        return self.save_provider(
            id=existing.id if existing is not None else None,
            name=name,
            base_url=base_url,
            api_key=api_key,
            default_model=default_model,
            enabled=True,
        )

    def save_provider(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
        enabled: bool,
        id: str | None = None,
    ) -> ProviderAccount:
        db = self._db()
        try:
            model = (
                db.query(ProviderAccountModel).filter(ProviderAccountModel.id == id).first()
                if id is not None
                else None
            )
            if model is None:
                model = ProviderAccountModel(
                    id=uuid4().hex,
                    name=name,
                    provider_type="openai_compatible",
                    base_url=base_url,
                    api_key=api_key,
                    default_model=default_model,
                    enabled=True,
                )
                db.add(model)
            else:
                model.provider_type = "openai_compatible"
                model.base_url = base_url
                model.default_model = default_model
                model.enabled = True
                if api_key:
                    model.api_key = api_key
            db.commit()
            db.refresh(model)
            return self._to_provider_account(model)
        finally:
            self._close(db)

    def get_provider_by_name(self, name: str) -> ProviderAccount | None:
        db = self._db()
        try:
            row = db.query(ProviderAccountModel).filter(ProviderAccountModel.name == name).first()
            return self._to_provider_account(row) if row is not None else None
        finally:
            self._close(db)

    def get_provider(self, provider_id: str) -> ProviderAccount | None:
        db = self._db()
        try:
            row = db.query(ProviderAccountModel).filter(ProviderAccountModel.id == provider_id).first()
            return self._to_provider_account(row) if row is not None else None
        finally:
            self._close(db)

    def list_configured_openai_providers(self) -> list[ProviderAccount]:
        db = self._db()
        try:
            rows = (
                db.query(ProviderAccountModel)
                .filter(
                    ProviderAccountModel.provider_type == "openai_compatible",
                    ProviderAccountModel.enabled.is_(True),
                    ProviderAccountModel.base_url != "",
                    ProviderAccountModel.api_key != "",
                )
                .order_by(ProviderAccountModel.created_at.asc(), ProviderAccountModel.id.asc())
                .all()
            )
            return [self._to_provider_account(row) for row in rows]
        finally:
            self._close(db)

    def has_routes(self) -> bool:
        db = self._db()
        try:
            return db.query(ProviderRouteModel.id).first() is not None
        finally:
            self._close(db)

    def list_routes(self, provider_group: str) -> list[ProviderRoute]:
        db = self._db()
        try:
            rows = (
                db.query(ProviderRouteModel)
                .filter(ProviderRouteModel.provider_group == provider_group)
                .order_by(ProviderRouteModel.priority.asc(), ProviderRouteModel.id.asc())
                .all()
            )
            return [self._to_provider_route(row) for row in rows]
        finally:
            self._close(db)

    def replace_routes(self, provider_group: str, entries: list[dict]) -> list[ProviderRoute]:
        db = self._db()
        try:
            db.query(ProviderRouteModel).filter(ProviderRouteModel.provider_group == provider_group).delete()
            db.flush()
            for priority, entry in enumerate(entries):
                db.add(
                    ProviderRouteModel(
                        id=uuid4().hex,
                        provider_group=provider_group,
                        provider_account_id=str(entry["provider_account_id"]),
                        model=str(entry["model"]),
                        priority=priority,
                        enabled=bool(entry.get("enabled", True)),
                    )
                )
            db.commit()
            rows = (
                db.query(ProviderRouteModel)
                .filter(ProviderRouteModel.provider_group == provider_group)
                .order_by(ProviderRouteModel.priority.asc(), ProviderRouteModel.id.asc())
                .all()
            )
            return [self._to_provider_route(row) for row in rows]
        finally:
            self._close(db)

    def get_llm_provider(self) -> ProviderAccount | None:
        db = self._db()
        try:
            row = (
                db.query(ProviderAccountModel)
                .filter(ProviderAccountModel.provider_type == "openai_compatible")
                .order_by(ProviderAccountModel.created_at.desc())
                .first()
            )
            return self._to_provider_account(row) if row is not None else None
        finally:
            self._close(db)

    def create_model(self, provider_account_id: str, name: str, capabilities: list[str]) -> ProviderModel:
        db = self._db()
        try:
            model = ProviderModelModel(
                id=uuid4().hex,
                provider_account_id=provider_account_id,
                name=name,
                capabilities=json.dumps(capabilities, ensure_ascii=False),
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return ProviderModel(
                id=model.id,
                provider_account_id=model.provider_account_id,
                name=model.name,
                capabilities=json.loads(model.capabilities),
                created_at=model.created_at,
            )
        finally:
            self._close(db)

    def create_quota_policy(self, scope_type: str, scope_id: str, daily_cost_limit: float) -> QuotaPolicy:
        db = self._db()
        try:
            model = QuotaPolicyModel(
                id=uuid4().hex,
                scope_type=scope_type,
                scope_id=scope_id,
                daily_cost_limit=daily_cost_limit,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return QuotaPolicy(
                id=model.id,
                scope_type=model.scope_type,
                scope_id=model.scope_id,
                daily_cost_limit=model.daily_cost_limit,
                created_at=model.created_at,
            )
        finally:
            self._close(db)

    def list_provider_accounts(self) -> list[ProviderAccount]:
        db = self._db()
        try:
            rows = db.query(ProviderAccountModel).order_by(ProviderAccountModel.created_at.desc()).all()
            return [
                self._to_provider_account(row)
                for row in rows
            ]
        finally:
            self._close(db)

    def list_quota_policies(self) -> list[QuotaPolicy]:
        db = self._db()
        try:
            rows = db.query(QuotaPolicyModel).order_by(QuotaPolicyModel.created_at.desc()).all()
            return [
                QuotaPolicy(
                    id=row.id,
                    scope_type=row.scope_type,
                    scope_id=row.scope_id,
                    daily_cost_limit=row.daily_cost_limit,
                    created_at=row.created_at,
                )
                for row in rows
            ]
        finally:
            self._close(db)

    @staticmethod
    def _to_provider_account(row: ProviderAccountModel) -> ProviderAccount:
        return ProviderAccount(
            id=row.id,
            name=row.name,
            provider_type=row.provider_type,
            base_url=row.base_url,
            api_key=row.api_key or "",
            default_model=row.default_model or "",
            enabled=row.enabled,
            created_at=row.created_at,
        )

    @staticmethod
    def _to_provider_route(row: ProviderRouteModel) -> ProviderRoute:
        return ProviderRoute(
            id=row.id,
            provider_group=row.provider_group,
            provider_account_id=row.provider_account_id,
            model=row.model,
            priority=row.priority,
            enabled=row.enabled,
        )
