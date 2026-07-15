from datetime import datetime

from sqlalchemy.dialects.sqlite import insert

from app.database import SessionLocal
from app.domain.repositories.system_settings_repo import SystemSettingsRepository

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
