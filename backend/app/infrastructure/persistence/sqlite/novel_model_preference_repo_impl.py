from app.domain.entities.novel_runtime import NovelModelPreference
from app.domain.repositories.novel_model_preference_repo import NovelModelPreferenceRepository

from .session import SessionLocal
from .schema import NovelModelPreferenceModel


class SQLiteNovelModelPreferenceRepository(NovelModelPreferenceRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    def save(self, preference: NovelModelPreference) -> NovelModelPreference:
        db = self._db()
        try:
            model = db.query(NovelModelPreferenceModel).filter(
                NovelModelPreferenceModel.owner_scope == preference.owner_scope,
                NovelModelPreferenceModel.scope_type == preference.scope_type,
                NovelModelPreferenceModel.scope_id == preference.scope_id,
                NovelModelPreferenceModel.task_type == preference.task_type,
            ).first()
            if model is None:
                model = NovelModelPreferenceModel(
                    owner_scope=preference.owner_scope,
                    scope_type=preference.scope_type,
                    scope_id=preference.scope_id,
                    task_type=preference.task_type,
                )
                db.add(model)
            model.model_ref = preference.model_ref
            model.provider_group = preference.provider_group
            db.commit()
            db.refresh(model)
            return self._to_domain(model)
        finally:
            self._close(db)

    def get(self, owner_scope: str, scope_type: str, scope_id: str, task_type: str) -> NovelModelPreference | None:
        db = self._db()
        try:
            model = db.query(NovelModelPreferenceModel).filter(
                NovelModelPreferenceModel.owner_scope == owner_scope,
                NovelModelPreferenceModel.scope_type == scope_type,
                NovelModelPreferenceModel.scope_id == scope_id,
                NovelModelPreferenceModel.task_type == task_type,
            ).first()
            return self._to_domain(model) if model else None
        finally:
            self._close(db)

    def delete(self, owner_scope: str, scope_type: str, scope_id: str, task_type: str) -> bool:
        db = self._db()
        try:
            count = db.query(NovelModelPreferenceModel).filter(
                NovelModelPreferenceModel.owner_scope == owner_scope,
                NovelModelPreferenceModel.scope_type == scope_type,
                NovelModelPreferenceModel.scope_id == scope_id,
                NovelModelPreferenceModel.task_type == task_type,
            ).delete(synchronize_session=False)
            db.commit()
            return count > 0
        finally:
            self._close(db)

    @staticmethod
    def _to_domain(model: NovelModelPreferenceModel) -> NovelModelPreference:
        return NovelModelPreference(
            owner_scope=model.owner_scope,
            scope_type=model.scope_type,
            scope_id=model.scope_id,
            task_type=model.task_type,
            model_ref=model.model_ref,
            provider_group=model.provider_group,
            updated_at=model.updated_at,
        )
