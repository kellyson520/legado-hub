import hashlib
import json
from datetime import datetime

from sqlalchemy.dialects.sqlite import insert

from app.infrastructure.persistence.sqlite.session import SessionLocal
from app.domain.repositories.system_settings_repo import (
    ConcurrentSettingsUpdateError,
    SystemSettingsRepository,
    VersionedSetting,
)

from .schema import SystemSettingModel


class SQLiteSystemSettingsRepository(SystemSettingsRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db) -> None:
        if self._session is None:
            db.close()

    def get_bool(self, key: str, default: bool = False) -> bool:
        db = self._db()
        try:
            row = db.query(SystemSettingModel).filter(SystemSettingModel.key == key).first()
            if row is None:
                return default
            if row.value == "true":
                return True
            if row.value == "false":
                return False
            return default
        finally:
            self._close(db)

    def set_bool(self, key: str, value: bool) -> None:
        self._set_value(key, "true" if value else "false")

    def get_int(self, key: str, default: int) -> int:
        db = self._db()
        try:
            row = db.query(SystemSettingModel).filter(SystemSettingModel.key == key).first()
            if row is None:
                return default
            try:
                return int(row.value)
            except (TypeError, ValueError):
                return default
        finally:
            self._close(db)

    def set_int(self, key: str, value: int) -> None:
        self._set_value(key, str(int(value)))

    def get_json(self, key: str, default: dict[str, object]) -> VersionedSetting:
        db = self._db()
        try:
            row = db.query(SystemSettingModel).filter(SystemSettingModel.key == key).first()
            if row is None:
                return VersionedSetting(value=dict(default), version=None, updated_at=None)
            try:
                value = json.loads(row.value)
            except (TypeError, json.JSONDecodeError):
                value = dict(default)
            if not isinstance(value, dict):
                value = dict(default)
            return self._to_versioned_setting(row, value)
        finally:
            self._close(db)

    def put_json(
        self,
        key: str,
        value: dict[str, object],
        expected_version: str | None,
    ) -> VersionedSetting:
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        db = self._db()
        try:
            row = db.query(SystemSettingModel).filter(SystemSettingModel.key == key).first()
            if row is None:
                if expected_version is not None:
                    raise ConcurrentSettingsUpdateError(key)
                row = SystemSettingModel(key=key, value=canonical, updated_at=datetime.utcnow())
                db.add(row)
                db.commit()
                db.refresh(row)
                return self._to_versioned_setting(row, value)

            if expected_version is None or expected_version != self._version(row):
                raise ConcurrentSettingsUpdateError(key)

            previous_value = row.value
            previous_updated_at = row.updated_at
            now = datetime.utcnow()
            updated = (
                db.query(SystemSettingModel)
                .filter(
                    SystemSettingModel.key == key,
                    SystemSettingModel.value == previous_value,
                    SystemSettingModel.updated_at == previous_updated_at,
                )
                .update({"value": canonical, "updated_at": now})
            )
            if updated != 1:
                db.rollback()
                raise ConcurrentSettingsUpdateError(key)
            db.commit()
            row = db.query(SystemSettingModel).filter(SystemSettingModel.key == key).first()
            assert row is not None
            return self._to_versioned_setting(row, value)
        finally:
            self._close(db)

    def _set_value(self, key: str, value: str) -> None:
        db = self._db()
        try:
            now = datetime.utcnow()
            statement = insert(SystemSettingModel).values(
                key=key,
                value=value,
                updated_at=now,
            )
            db.execute(
                statement.on_conflict_do_update(
                    index_elements=[SystemSettingModel.key],
                    set_={"value": statement.excluded.value, "updated_at": now},
                )
            )
            db.commit()
        finally:
            self._close(db)

    @classmethod
    def _to_versioned_setting(
        cls,
        row: SystemSettingModel,
        value: dict[str, object],
    ) -> VersionedSetting:
        return VersionedSetting(
            value=dict(value),
            version=cls._version(row),
            updated_at=row.updated_at,
        )

    @staticmethod
    def _version(row: SystemSettingModel) -> str:
        updated_at = row.updated_at.isoformat() if row.updated_at else ""
        payload = f"{row.key}\n{row.value}\n{updated_at}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
