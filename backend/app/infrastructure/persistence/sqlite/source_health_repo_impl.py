import json

from app.database import SessionLocal
from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun
from app.domain.repositories.source_health_repo import SourceHealthRepository

from .schema import SourceHealthSnapshotModel, SourceProbeRunModel


class SQLiteSourceHealthRepository(SourceHealthRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    @staticmethod
    def _loads_dict(raw: str | None) -> dict:
        if not raw:
            return {}
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _dump_json(value: dict) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    def _snapshot_to_entity(self, model: SourceHealthSnapshotModel) -> SourceHealthSnapshot:
        return SourceHealthSnapshot(
            source_id=model.source_id,
            source_name=model.source_name,
            source_url=model.source_url,
            health_status=model.health_status,
            search_status=model.search_status,
            toc_status=model.toc_status,
            content_status=model.content_status,
            failure_reason=model.failure_reason,
            decision_confidence=model.decision_confidence,
            route_policy=model.route_policy,
            route_score=float(model.route_score or 0),
            consecutive_failures=model.consecutive_failures,
            consecutive_successes=model.consecutive_successes,
            last_success_at=model.last_success_at,
            last_probe_at=model.last_probe_at,
            next_probe_at=model.next_probe_at,
            metadata=self._loads_dict(model.metadata_json),
        )

    def _run_to_entity(self, model: SourceProbeRunModel) -> SourceProbeRun:
        return SourceProbeRun(
            id=model.id,
            source_id=model.source_id,
            source_name=model.source_name,
            probe_mode=model.probe_mode,
            keyword=model.keyword,
            overall_status=model.overall_status,
            failure_reason=model.failure_reason,
            search_result=self._loads_dict(model.search_result),
            toc_result=self._loads_dict(model.toc_result),
            content_result=self._loads_dict(model.content_result),
            summary=self._loads_dict(model.summary),
            created_at=model.created_at,
        )

    def get_snapshot(self, source_id: int) -> SourceHealthSnapshot | None:
        db = self._db()
        try:
            row = db.query(SourceHealthSnapshotModel).filter(SourceHealthSnapshotModel.source_id == source_id).first()
            return self._snapshot_to_entity(row) if row else None
        finally:
            self._close(db)

    def list_snapshots(
        self,
        statuses: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SourceHealthSnapshot], int]:
        db = self._db()
        try:
            query = db.query(SourceHealthSnapshotModel).order_by(SourceHealthSnapshotModel.source_id.asc())
            if statuses:
                query = query.filter(SourceHealthSnapshotModel.health_status.in_(statuses))
            total = query.count()
            rows = query.offset(offset).limit(limit).all()
            return [self._snapshot_to_entity(row) for row in rows], total
        finally:
            self._close(db)

    def upsert_snapshot(self, snapshot: SourceHealthSnapshot) -> SourceHealthSnapshot:
        db = self._db()
        try:
            row = db.query(SourceHealthSnapshotModel).filter(SourceHealthSnapshotModel.source_id == snapshot.source_id).first()
            if row is None:
                row = SourceHealthSnapshotModel(source_id=snapshot.source_id)
                db.add(row)
            row.source_name = snapshot.source_name
            row.source_url = snapshot.source_url
            row.health_status = snapshot.health_status
            row.search_status = snapshot.search_status
            row.toc_status = snapshot.toc_status
            row.content_status = snapshot.content_status
            row.failure_reason = snapshot.failure_reason
            row.decision_confidence = snapshot.decision_confidence
            row.route_policy = snapshot.route_policy
            row.route_score = snapshot.route_score
            row.consecutive_failures = snapshot.consecutive_failures
            row.consecutive_successes = snapshot.consecutive_successes
            row.last_success_at = snapshot.last_success_at
            row.last_probe_at = snapshot.last_probe_at
            row.next_probe_at = snapshot.next_probe_at
            row.metadata_json = self._dump_json(snapshot.metadata)
            db.commit()
            db.refresh(row)
            return self._snapshot_to_entity(row)
        finally:
            self._close(db)

    def record_probe_run(self, run: SourceProbeRun) -> SourceProbeRun:
        db = self._db()
        try:
            row = SourceProbeRunModel(
                id=run.id,
                source_id=run.source_id,
                source_name=run.source_name,
                probe_mode=run.probe_mode,
                keyword=run.keyword,
                overall_status=run.overall_status,
                failure_reason=run.failure_reason,
                search_result=self._dump_json(run.search_result),
                toc_result=self._dump_json(run.toc_result),
                content_result=self._dump_json(run.content_result),
                summary=self._dump_json(run.summary),
                created_at=run.created_at,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._run_to_entity(row)
        finally:
            self._close(db)

    def list_probe_runs(self, source_id: int, limit: int = 20) -> list[SourceProbeRun]:
        db = self._db()
        try:
            rows = (
                db.query(SourceProbeRunModel)
                .filter(SourceProbeRunModel.source_id == source_id)
                .order_by(SourceProbeRunModel.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._run_to_entity(row) for row in rows]
        finally:
            self._close(db)
