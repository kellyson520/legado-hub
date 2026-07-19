import json

from sqlalchemy import and_, case, func, or_

from app.core.pagination import LIKE_ESCAPE, like_pattern
from app.infrastructure.persistence.sqlite.session import SessionLocal
from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun
from app.domain.repositories.source_health_repo import SourceHealthRepository

from .schema import BookSourceModel, SourceHealthSnapshotModel, SourceProbeRunModel


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

    def list_book_source_health_inventory(
        self,
        statuses: list[str] | None = None,
        search: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SourceHealthSnapshot], int]:
        db = self._db()
        try:
            derived_status = func.coalesce(SourceHealthSnapshotModel.health_status, "unknown")
            normalized_search = search.strip()
            search_pattern = like_pattern(normalized_search)
            count_query = db.query(func.count(BookSourceModel.id)).outerjoin(
                SourceHealthSnapshotModel,
                SourceHealthSnapshotModel.source_id == BookSourceModel.id,
            )
            if statuses:
                count_query = count_query.filter(derived_status.in_(statuses))
            if normalized_search:
                count_query = count_query.filter(
                    or_(
                        BookSourceModel.bookSourceName.ilike(search_pattern, escape=LIKE_ESCAPE),
                        BookSourceModel.bookSourceUrl.ilike(search_pattern, escape=LIKE_ESCAPE),
                    )
                )
            total = int(count_query.scalar() or 0)

            query = (
                db.query(
                    BookSourceModel.id.label("book_source_id"),
                    BookSourceModel.bookSourceName.label("book_source_name"),
                    BookSourceModel.bookSourceUrl.label("book_source_url"),
                    SourceHealthSnapshotModel.source_id.label("snapshot_source_id"),
                    SourceHealthSnapshotModel.source_name.label("snapshot_source_name"),
                    SourceHealthSnapshotModel.source_url.label("snapshot_source_url"),
                    SourceHealthSnapshotModel.health_status.label("snapshot_health_status"),
                    SourceHealthSnapshotModel.search_status.label("snapshot_search_status"),
                    SourceHealthSnapshotModel.toc_status.label("snapshot_toc_status"),
                    SourceHealthSnapshotModel.content_status.label("snapshot_content_status"),
                    SourceHealthSnapshotModel.failure_reason.label("snapshot_failure_reason"),
                    SourceHealthSnapshotModel.decision_confidence.label("snapshot_decision_confidence"),
                    SourceHealthSnapshotModel.route_policy.label("snapshot_route_policy"),
                    SourceHealthSnapshotModel.route_score.label("snapshot_route_score"),
                    SourceHealthSnapshotModel.consecutive_failures.label("snapshot_consecutive_failures"),
                    SourceHealthSnapshotModel.consecutive_successes.label("snapshot_consecutive_successes"),
                    SourceHealthSnapshotModel.last_success_at.label("snapshot_last_success_at"),
                    SourceHealthSnapshotModel.last_probe_at.label("snapshot_last_probe_at"),
                    SourceHealthSnapshotModel.next_probe_at.label("snapshot_next_probe_at"),
                    SourceHealthSnapshotModel.metadata_json.label("snapshot_metadata_json"),
                )
                .outerjoin(
                    SourceHealthSnapshotModel,
                    SourceHealthSnapshotModel.source_id == BookSourceModel.id,
                )
                .order_by(BookSourceModel.id.asc())
            )
            if statuses:
                query = query.filter(derived_status.in_(statuses))
            if normalized_search:
                query = query.filter(
                    or_(
                        BookSourceModel.bookSourceName.ilike(search_pattern, escape=LIKE_ESCAPE),
                        BookSourceModel.bookSourceUrl.ilike(search_pattern, escape=LIKE_ESCAPE),
                    )
                )
            rows = query.offset(offset).limit(limit).all()
            return [self._inventory_row_to_snapshot(row) for row in rows], total
        finally:
            self._close(db)

    def count_book_source_health_statuses(
        self,
        statuses: list[str] | None = None,
        search: str = "",
    ) -> dict[str, int]:
        db = self._db()
        try:
            derived_status = func.coalesce(SourceHealthSnapshotModel.health_status, "unknown")
            inventory_status = case(
                (
                    or_(
                        SourceHealthSnapshotModel.source_id.is_(None),
                        and_(
                            derived_status == "unknown",
                            SourceHealthSnapshotModel.failure_reason == "not_probed",
                        ),
                    ),
                    "unprobed",
                ),
                else_=derived_status,
            )
            normalized_search = search.strip()
            search_pattern = like_pattern(normalized_search)
            query = (
                db.query(inventory_status.label("inventory_status"), func.count(BookSourceModel.id))
                .outerjoin(
                    SourceHealthSnapshotModel,
                    SourceHealthSnapshotModel.source_id == BookSourceModel.id,
                )
            )
            if statuses:
                query = query.filter(derived_status.in_(statuses))
            if normalized_search:
                query = query.filter(
                    or_(
                        BookSourceModel.bookSourceName.ilike(search_pattern, escape=LIKE_ESCAPE),
                        BookSourceModel.bookSourceUrl.ilike(search_pattern, escape=LIKE_ESCAPE),
                    )
                )
            grouped = query.group_by(inventory_status).all()
            counts = {str(status): int(count) for status, count in grouped}
            for status in ("healthy", "degraded", "blocked", "dead", "unprobed", "unknown"):
                counts.setdefault(status, 0)
            counts["total"] = sum(counts.values())
            return counts
        finally:
            self._close(db)

    def _inventory_row_to_snapshot(self, row) -> SourceHealthSnapshot:
        if row.snapshot_source_id is None:
            return SourceHealthSnapshot(
                source_id=row.book_source_id,
                source_name=row.book_source_name,
                source_url=row.book_source_url,
                health_status="unknown",
                search_status="unknown",
                toc_status="unknown",
                content_status="unknown",
                failure_reason="not_probed",
                decision_confidence="low",
                route_policy="probe_only",
                route_score=10.0,
            )
        return SourceHealthSnapshot(
            source_id=row.snapshot_source_id,
            source_name=row.snapshot_source_name,
            source_url=row.snapshot_source_url,
            health_status=row.snapshot_health_status,
            search_status=row.snapshot_search_status,
            toc_status=row.snapshot_toc_status,
            content_status=row.snapshot_content_status,
            failure_reason=row.snapshot_failure_reason,
            decision_confidence=row.snapshot_decision_confidence,
            route_policy=row.snapshot_route_policy,
            route_score=float(row.snapshot_route_score or 0),
            consecutive_failures=row.snapshot_consecutive_failures,
            consecutive_successes=row.snapshot_consecutive_successes,
            last_success_at=row.snapshot_last_success_at,
            last_probe_at=row.snapshot_last_probe_at,
            next_probe_at=row.snapshot_next_probe_at,
            metadata=self._loads_dict(row.snapshot_metadata_json),
        )

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

    def list_probe_candidate_ids(self, limit: int = 20) -> list[int]:
        db = self._db()
        try:
            unprobed_first = case(
                (SourceHealthSnapshotModel.source_id.is_(None), 0),
                else_=1,
            )
            no_probe_time_first = case(
                (SourceHealthSnapshotModel.last_probe_at.is_(None), 0),
                else_=1,
            )
            rows = (
                db.query(BookSourceModel.id)
                .outerjoin(
                    SourceHealthSnapshotModel,
                    SourceHealthSnapshotModel.source_id == BookSourceModel.id,
                )
                .filter(BookSourceModel.enabled == True)
                .order_by(
                    unprobed_first.asc(),
                    no_probe_time_first.asc(),
                    SourceHealthSnapshotModel.last_probe_at.asc(),
                    BookSourceModel.id.asc(),
                )
                .limit(max(int(limit), 0))
                .all()
            )
            return [int(row[0]) for row in rows]
        finally:
            self._close(db)
