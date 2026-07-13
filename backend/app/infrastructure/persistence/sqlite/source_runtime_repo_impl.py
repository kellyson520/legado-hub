import json
from datetime import datetime
from uuid import uuid4

from app.database import SessionLocal
from app.domain.entities.source_runtime import (
    SourceDefinition,
    SourceDeployment,
    SourceHealthEvent,
    SourceTestRun,
    SourceVersion,
)
from app.domain.repositories.source_runtime_repo import SourceRuntimeRepository

from .schema import (
    SourceDefinitionModel,
    SourceDeploymentModel,
    SourceHealthEventModel,
    SourceRunStepModel,
    SourceTestRunModel,
    SourceVersionModel,
)


def _loads_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


def _loads_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    value = json.loads(raw)
    return value if isinstance(value, list) else []


class SQLiteSourceRuntimeRepository(SourceRuntimeRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    def _definition_to_entity(self, model: SourceDefinitionModel) -> SourceDefinition:
        return SourceDefinition(
            id=model.id,
            source_type=model.source_type,
            source_key=model.source_key,
            source_name=model.source_name,
            source_group=model.source_group,
            enabled=model.enabled,
            created_at=model.created_at,
        )

    def _version_to_entity(self, model: SourceVersionModel) -> SourceVersion:
        return SourceVersion(
            id=model.id,
            source_definition_id=model.source_definition_id,
            source_type=model.source_type,
            source_id=model.source_id,
            status=model.status,
            payload=_loads_dict(model.payload),
            created_by=model.created_by,
            created_at=model.created_at,
            published_at=model.published_at,
        )

    def _run_to_entity(self, model: SourceTestRunModel) -> SourceTestRun:
        return SourceTestRun(
            id=model.id,
            source_version_id=model.source_version_id,
            trigger=model.trigger,
            score=model.score,
            grade=model.grade,
            step_results=_loads_dict(model.step_results),
            diagnostics=_loads_list(model.diagnostics),
            created_at=model.created_at,
        )

    def _deployment_to_entity(self, model: SourceDeploymentModel) -> SourceDeployment:
        return SourceDeployment(
            id=model.id,
            source_version_id=model.source_version_id,
            action=model.action,
            status=model.status,
            quality_gate=_loads_dict(model.quality_gate),
            actor_id=model.actor_id,
            created_at=model.created_at,
        )

    def _health_to_entity(self, model: SourceHealthEventModel) -> SourceHealthEvent:
        return SourceHealthEvent(
            id=model.id,
            source_version_id=model.source_version_id,
            event_type=model.event_type,
            detail=_loads_dict(model.detail),
            created_at=model.created_at,
        )

    def ensure_source_definition(
        self,
        source_type: str,
        source_key: str,
        source_name: str = "",
        source_group: str = "default",
    ) -> SourceDefinition:
        db = self._db()
        try:
            model = (
                db.query(SourceDefinitionModel)
                .filter(
                    SourceDefinitionModel.source_type == source_type,
                    SourceDefinitionModel.source_key == source_key,
                )
                .first()
            )
            if model is None:
                model = SourceDefinitionModel(
                    source_type=source_type,
                    source_key=source_key,
                    source_name=source_name or source_key,
                    source_group=source_group,
                    enabled=True,
                )
                db.add(model)
                db.commit()
                db.refresh(model)
            return self._definition_to_entity(model)
        finally:
            self._close(db)

    def create_candidate_version(
        self,
        source_type: str,
        source_id: str,
        payload: dict,
        created_by: str,
    ) -> SourceVersion:
        db = self._db()
        try:
            definition = self.ensure_source_definition(source_type=source_type, source_key=source_id)
            model = SourceVersionModel(
                id=uuid4().hex,
                source_definition_id=definition.id,
                source_type=source_type,
                source_id=source_id,
                status="candidate",
                payload=json.dumps(payload, ensure_ascii=False),
                created_by=created_by,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._version_to_entity(model)
        finally:
            self._close(db)

    def get_version(self, version_id: str) -> SourceVersion | None:
        db = self._db()
        try:
            model = db.query(SourceVersionModel).filter(SourceVersionModel.id == version_id).first()
            return self._version_to_entity(model) if model else None
        finally:
            self._close(db)

    def list_versions(self, source_type: str, source_id: str) -> list[SourceVersion]:
        db = self._db()
        try:
            rows = (
                db.query(SourceVersionModel)
                .filter(
                    SourceVersionModel.source_type == source_type,
                    SourceVersionModel.source_id == source_id,
                )
                .order_by(SourceVersionModel.created_at.desc())
                .all()
            )
            return [self._version_to_entity(row) for row in rows]
        finally:
            self._close(db)

    def list_recent_versions(self, *, status: str | None = None, limit: int = 50) -> list[SourceVersion]:
        db = self._db()
        try:
            query = db.query(SourceVersionModel)
            if status is not None:
                query = query.filter(SourceVersionModel.status == status)
            rows = (
                query.order_by(SourceVersionModel.created_at.desc(), SourceVersionModel.id.desc())
                .limit(limit)
                .all()
            )
            return [self._version_to_entity(row) for row in rows]
        finally:
            self._close(db)

    def list_published_versions(self) -> list[SourceVersion]:
        db = self._db()
        try:
            rows = (
                db.query(SourceVersionModel)
                .filter(SourceVersionModel.status == "published")
                .order_by(SourceVersionModel.created_at.desc())
                .all()
            )
            return [self._version_to_entity(row) for row in rows]
        finally:
            self._close(db)

    def record_test_run(
        self,
        source_version_id: str,
        trigger: str,
        score: int,
        grade: str,
        step_results: dict,
        diagnostics: list[str] | None = None,
    ) -> SourceTestRun:
        db = self._db()
        try:
            model = SourceTestRunModel(
                id=uuid4().hex,
                source_version_id=source_version_id,
                trigger=trigger,
                score=score,
                grade=grade,
                step_results=json.dumps(step_results, ensure_ascii=False),
                diagnostics=json.dumps(diagnostics or [], ensure_ascii=False),
            )
            db.add(model)
            db.flush()
            for step_name, detail in step_results.items():
                db.add(
                    SourceRunStepModel(
                        test_run_id=model.id,
                        step_name=step_name,
                        passed=bool(detail.get("passed")),
                        elapsed_ms=int(detail.get("elapsed_ms", 0) or 0),
                        detail=json.dumps(detail, ensure_ascii=False),
                    )
                )
            db.commit()
            db.refresh(model)
            return self._run_to_entity(model)
        finally:
            self._close(db)

    def list_test_runs(self, source_version_id: str | None = None) -> list[SourceTestRun]:
        db = self._db()
        try:
            query = db.query(SourceTestRunModel)
            if source_version_id:
                query = query.filter(SourceTestRunModel.source_version_id == source_version_id)
            rows = query.order_by(SourceTestRunModel.created_at.desc()).all()
            return [self._run_to_entity(row) for row in rows]
        finally:
            self._close(db)

    def record_deployment(
        self,
        source_version_id: str,
        action: str,
        status: str,
        quality_gate: dict,
        actor_id: str,
    ) -> SourceDeployment:
        db = self._db()
        try:
            model = SourceDeploymentModel(
                id=uuid4().hex,
                source_version_id=source_version_id,
                action=action,
                status=status,
                quality_gate=json.dumps(quality_gate, ensure_ascii=False),
                actor_id=actor_id,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._deployment_to_entity(model)
        finally:
            self._close(db)

    def record_health_event(
        self,
        source_version_id: str,
        event_type: str,
        detail: dict,
    ) -> SourceHealthEvent:
        db = self._db()
        try:
            model = SourceHealthEventModel(
                source_version_id=source_version_id,
                event_type=event_type,
                detail=json.dumps(detail, ensure_ascii=False),
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._health_to_entity(model)
        finally:
            self._close(db)

    def update_version_status(self, version_id: str, status: str) -> SourceVersion:
        db = self._db()
        try:
            model = db.query(SourceVersionModel).filter(SourceVersionModel.id == version_id).first()
            if model is None:
                raise KeyError(version_id)
            model.status = status
            if status == "published" and model.published_at is None:
                model.published_at = datetime.utcnow()
            db.commit()
            db.refresh(model)
            return self._version_to_entity(model)
        finally:
            self._close(db)

    def update_version_payload(self, version_id: str, payload: dict) -> SourceVersion:
        db = self._db()
        try:
            model = db.query(SourceVersionModel).filter(SourceVersionModel.id == version_id).first()
            if model is None:
                raise KeyError(version_id)
            model.payload = json.dumps(payload, ensure_ascii=False)
            db.commit()
            db.refresh(model)
            return self._version_to_entity(model)
        finally:
            self._close(db)

    def list_deployments(self, source_version_id: str | None = None) -> list[SourceDeployment]:
        db = self._db()
        try:
            query = db.query(SourceDeploymentModel)
            if source_version_id:
                query = query.filter(SourceDeploymentModel.source_version_id == source_version_id)
            rows = query.order_by(SourceDeploymentModel.created_at.desc()).all()
            return [self._deployment_to_entity(row) for row in rows]
        finally:
            self._close(db)
