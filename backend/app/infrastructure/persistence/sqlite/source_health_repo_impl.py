import json
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import and_, case, func, or_, text

from app.core.pagination import LIKE_ESCAPE, like_pattern
from app.infrastructure.persistence.sqlite.session import SessionLocal
from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun
from app.domain.repositories.source_health_repo import SourceHealthRepository

from .schema import (
    BookSourceModel,
    SourceHealthProbeLeaseModel,
    SourceHealthSnapshotModel,
    SourceProbeRunModel,
)


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

    def _apply_snapshot_row(self, row: SourceHealthSnapshotModel, snapshot: SourceHealthSnapshot) -> None:
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

    def _new_probe_run_row(self, run: SourceProbeRun) -> SourceProbeRunModel:
        return SourceProbeRunModel(
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

    @staticmethod
    def _normalized_health_status_expression():
        raw_status = func.coalesce(SourceHealthSnapshotModel.health_status, "unknown")
        # Older probes treated an absent fixed keyword as a degraded source.
        # Keep that historical data from influencing routing or inventory.
        return case(
            (
                and_(
                    raw_status == "degraded",
                    SourceHealthSnapshotModel.failure_reason == "keyword_no_result",
                ),
                "unknown",
            ),
            else_=raw_status,
        )

    @classmethod
    def _inventory_status_expression(cls):
        derived_status = cls._normalized_health_status_expression()
        unprobed = or_(
            SourceHealthSnapshotModel.source_id.is_(None),
            and_(
                derived_status == "unknown",
                SourceHealthSnapshotModel.failure_reason == "not_probed",
            ),
        )
        return case(
            (BookSourceModel.enabled == False, "disabled"),
            (unprobed, "unprobed"),
            else_=derived_status,
        )

    def _snapshot_to_entity(self, model: SourceHealthSnapshotModel) -> SourceHealthSnapshot:
        legacy_no_match = (
            model.health_status == "degraded"
            and model.failure_reason == "keyword_no_result"
        )
        return SourceHealthSnapshot(
            source_id=model.source_id,
            source_name=model.source_name,
            source_url=model.source_url,
            health_status="unknown" if legacy_no_match else model.health_status,
            search_status=model.search_status,
            toc_status=model.toc_status,
            content_status=model.content_status,
            failure_reason=model.failure_reason,
            decision_confidence="low" if legacy_no_match else model.decision_confidence,
            route_policy="probe_only" if legacy_no_match else model.route_policy,
            route_score=10.0 if legacy_no_match else float(model.route_score or 0),
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
            normalized_status = self._normalized_health_status_expression()
            query = db.query(SourceHealthSnapshotModel).order_by(SourceHealthSnapshotModel.source_id.asc())
            if statuses:
                query = query.filter(normalized_status.in_(statuses))
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
            inventory_status = self._inventory_status_expression()
            normalized_search = search.strip()
            search_pattern = like_pattern(normalized_search)
            count_query = db.query(func.count(BookSourceModel.id)).outerjoin(
                SourceHealthSnapshotModel,
                SourceHealthSnapshotModel.source_id == BookSourceModel.id,
            )
            if statuses:
                count_query = count_query.filter(inventory_status.in_(statuses))
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
                    BookSourceModel.enabled.label("book_source_enabled"),
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
                query = query.filter(inventory_status.in_(statuses))
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
            inventory_status = self._inventory_status_expression()
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
                query = query.filter(inventory_status.in_(statuses))
            if normalized_search:
                query = query.filter(
                    or_(
                        BookSourceModel.bookSourceName.ilike(search_pattern, escape=LIKE_ESCAPE),
                        BookSourceModel.bookSourceUrl.ilike(search_pattern, escape=LIKE_ESCAPE),
                    )
                )
            grouped = query.group_by(inventory_status).all()
            counts = {str(status): int(count) for status, count in grouped}
            for status in ("healthy", "degraded", "blocked", "dead", "unprobed", "unknown", "disabled"):
                counts.setdefault(status, 0)
            counts["total"] = sum(counts.values())
            return counts
        finally:
            self._close(db)

    def _inventory_row_to_snapshot(self, row) -> SourceHealthSnapshot:
        if not bool(row.book_source_enabled):
            return SourceHealthSnapshot(
                source_id=row.book_source_id,
                source_name=row.book_source_name,
                source_url=row.book_source_url,
                health_status="disabled",
                search_status="skipped",
                toc_status="skipped",
                content_status="skipped",
                failure_reason="disabled",
                decision_confidence="high",
                route_policy="skip",
                route_score=0.0,
                metadata=self._loads_dict(row.snapshot_metadata_json),
            )
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
        legacy_no_match = (
            row.snapshot_health_status == "degraded"
            and row.snapshot_failure_reason == "keyword_no_result"
        )
        return SourceHealthSnapshot(
            source_id=row.snapshot_source_id,
            source_name=row.snapshot_source_name,
            source_url=row.snapshot_source_url,
            health_status="unknown" if legacy_no_match else row.snapshot_health_status,
            search_status=row.snapshot_search_status,
            toc_status=row.snapshot_toc_status,
            content_status=row.snapshot_content_status,
            failure_reason=row.snapshot_failure_reason,
            decision_confidence="low" if legacy_no_match else row.snapshot_decision_confidence,
            route_policy="probe_only" if legacy_no_match else row.snapshot_route_policy,
            route_score=10.0 if legacy_no_match else float(row.snapshot_route_score or 0),
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
            self._apply_snapshot_row(row, snapshot)
            db.commit()
            db.refresh(row)
            return self._snapshot_to_entity(row)
        finally:
            self._close(db)

    def record_probe_run(self, run: SourceProbeRun) -> SourceProbeRun:
        db = self._db()
        try:
            row = self._new_probe_run_row(run)
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._run_to_entity(row)
        finally:
            self._close(db)

    def record_probe_failure(
        self,
        snapshot: SourceHealthSnapshot,
        run: SourceProbeRun,
        *,
        source_status: str,
        error_msg: str,
        last_check_time: datetime,
        worker_id: str,
        lease_token: str,
        write_deadline: float | None = None,
    ) -> tuple[SourceHealthSnapshot, SourceProbeRun]:
        return self._record_probe_state(
            snapshot,
            run,
            source_status=source_status,
            error_msg=error_msg,
            last_check_time=last_check_time,
            worker_id=worker_id,
            lease_token=lease_token,
            write_deadline=write_deadline,
        )

    def record_probe_result(
        self,
        snapshot: SourceHealthSnapshot,
        run: SourceProbeRun,
        *,
        source_status: str,
        error_msg: str,
        last_check_time: datetime,
        worker_id: str,
        lease_token: str,
        write_deadline: float | None = None,
    ) -> tuple[SourceHealthSnapshot, SourceProbeRun]:
        return self._record_probe_state(
            snapshot,
            run,
            source_status=source_status,
            error_msg=error_msg,
            last_check_time=last_check_time,
            worker_id=worker_id,
            lease_token=lease_token,
            write_deadline=write_deadline,
        )

    def _record_probe_state(
        self,
        snapshot: SourceHealthSnapshot,
        run: SourceProbeRun,
        *,
        source_status: str,
        error_msg: str,
        last_check_time: datetime,
        worker_id: str,
        lease_token: str,
        write_deadline: float | None = None,
    ) -> tuple[SourceHealthSnapshot, SourceProbeRun]:
        db = self._db()
        try:
            if write_deadline is not None and time.monotonic() >= write_deadline:
                raise TimeoutError("probe write deadline exceeded")
            # Validate and persist under the same SQLite write lock. A worker
            # whose lease expires while waiting cannot commit a late result
            # after another worker has reclaimed the source.
            db.execute(text("BEGIN IMMEDIATE"))
            if write_deadline is not None and time.monotonic() >= write_deadline:
                raise TimeoutError("probe write deadline exceeded")
            self._assert_probe_lease(
                db,
                source_id=snapshot.source_id,
                worker_id=worker_id,
                lease_token=lease_token,
            )
            source = db.query(BookSourceModel).filter(BookSourceModel.id == snapshot.source_id).first()
            if source is None:
                raise ValueError(f"book source not found: {snapshot.source_id}")

            row = (
                db.query(SourceHealthSnapshotModel)
                .filter(SourceHealthSnapshotModel.source_id == snapshot.source_id)
                .first()
            )
            if row is None:
                row = SourceHealthSnapshotModel(source_id=snapshot.source_id)
                db.add(row)
            self._apply_snapshot_row(row, snapshot)

            run_row = self._new_probe_run_row(run)
            db.add(run_row)
            source.sourceStatus = source_status
            source.errorMsg = error_msg
            source.lastCheckTime = last_check_time
            if write_deadline is not None and time.monotonic() >= write_deadline:
                raise TimeoutError("probe write deadline exceeded")
            db.commit()
            db.refresh(row)
            db.refresh(run_row)
            return self._snapshot_to_entity(row), self._run_to_entity(run_row)
        except Exception:
            db.rollback()
            raise
        finally:
            self._close(db)

    @staticmethod
    def _assert_probe_lease(db, *, source_id: int, worker_id: str, lease_token: str) -> None:
        if not str(worker_id or "").strip() or not str(lease_token or "").strip():
            raise PermissionError("probe lease is required")
        lease = (
            db.query(SourceHealthProbeLeaseModel)
            .filter(
                SourceHealthProbeLeaseModel.source_id == int(source_id),
                SourceHealthProbeLeaseModel.worker_id == str(worker_id),
                SourceHealthProbeLeaseModel.lease_token == str(lease_token),
            )
            .first()
        )
        if lease is None:
            raise PermissionError("probe lease is not held by this worker")
        expires_at = lease.lease_expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at is None or expires_at <= datetime.now(timezone.utc):
            raise PermissionError("probe lease has expired")

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

    def list_probe_candidate_ids(self, limit: int | None = 20) -> list[int]:
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
            query = (
                db.query(BookSourceModel.id)
                .outerjoin(
                    SourceHealthSnapshotModel,
                    SourceHealthSnapshotModel.source_id == BookSourceModel.id,
                )
                .filter(BookSourceModel.enabled == True)
                .filter(
                    or_(
                        SourceHealthSnapshotModel.source_id.is_(None),
                        SourceHealthSnapshotModel.next_probe_at.is_(None),
                        SourceHealthSnapshotModel.next_probe_at <= datetime.now(timezone.utc),
                    )
                )
                .order_by(
                    unprobed_first.asc(),
                    no_probe_time_first.asc(),
                    SourceHealthSnapshotModel.last_probe_at.asc(),
                    BookSourceModel.id.asc(),
                )
            )
            if limit is not None:
                query = query.limit(max(int(limit), 0))
            rows = query.all()
            return [int(row[0]) for row in rows]
        finally:
            self._close(db)

    def claim_probe_candidate_ids(
        self,
        limit: int | None = 20,
        *,
        worker_id: str,
        lease_seconds: int = 1800,
    ) -> list[int]:
        return list(
            self.claim_probe_candidate_leases(
                limit=limit,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            ).keys()
        )

    def claim_probe_candidate_leases(
        self,
        limit: int | None = 20,
        *,
        worker_id: str,
        lease_seconds: int = 1800,
    ) -> dict[int, str]:
        normalized_limit = None if limit is None else max(int(limit), 0)
        if normalized_limit == 0:
            return {}
        if not str(worker_id or "").strip():
            raise ValueError("worker_id is required")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=max(int(lease_seconds), 1))
        db = self._db()
        try:
            db.execute(text("BEGIN IMMEDIATE"))
            self._delete_expired_leases(db, now)
            source_ids = self._select_due_source_ids(db, now, limit=normalized_limit)
            leases = {}
            for source_id in source_ids:
                token = uuid4().hex
                leases[source_id] = token
                db.add(
                    SourceHealthProbeLeaseModel(
                        source_id=source_id,
                        worker_id=str(worker_id),
                        lease_token=token,
                        claimed_at=now,
                        lease_expires_at=expires_at,
                    )
                )
            db.commit()
            return leases
        except Exception:
            db.rollback()
            raise
        finally:
            self._close(db)

    def claim_probe_source_leases(
        self,
        source_ids: list[int],
        *,
        worker_id: str,
        lease_seconds: int = 1800,
    ) -> dict[int, str]:
        normalized_ids = list(dict.fromkeys(int(source_id) for source_id in source_ids or []))
        if not normalized_ids:
            return {}
        if not str(worker_id or "").strip():
            raise ValueError("worker_id is required")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=max(int(lease_seconds), 1))
        db = self._db()
        try:
            db.execute(text("BEGIN IMMEDIATE"))
            self._delete_expired_leases(db, now)
            active_lease = and_(
                SourceHealthProbeLeaseModel.source_id == BookSourceModel.id,
                SourceHealthProbeLeaseModel.lease_expires_at > now,
            )
            rows = (
                db.query(BookSourceModel.id)
                .outerjoin(SourceHealthProbeLeaseModel, active_lease)
                .filter(BookSourceModel.id.in_(normalized_ids))
                .filter(BookSourceModel.enabled == True)
                .filter(SourceHealthProbeLeaseModel.source_id.is_(None))
                .all()
            )
            available = {int(row[0]) for row in rows}
            leases = {}
            for source_id in normalized_ids:
                if source_id not in available:
                    continue
                token = uuid4().hex
                leases[source_id] = token
                db.add(
                    SourceHealthProbeLeaseModel(
                        source_id=source_id,
                        worker_id=str(worker_id),
                        lease_token=token,
                        claimed_at=now,
                        lease_expires_at=expires_at,
                    )
                )
            db.commit()
            return leases
        except Exception:
            db.rollback()
            raise
        finally:
            self._close(db)

    @staticmethod
    def _delete_expired_leases(db, now: datetime) -> None:
        db.query(SourceHealthProbeLeaseModel).filter(
            SourceHealthProbeLeaseModel.lease_expires_at <= now,
        ).delete(synchronize_session=False)

    @staticmethod
    def _select_due_source_ids(db, now: datetime, *, limit: int | None) -> list[int]:
        unprobed_first = case(
            (SourceHealthSnapshotModel.source_id.is_(None), 0),
            else_=1,
        )
        no_probe_time_first = case(
            (SourceHealthSnapshotModel.last_probe_at.is_(None), 0),
            else_=1,
        )
        active_lease = and_(
            SourceHealthProbeLeaseModel.source_id == BookSourceModel.id,
            SourceHealthProbeLeaseModel.lease_expires_at > now,
        )
        query = (
            db.query(BookSourceModel.id)
            .outerjoin(
                SourceHealthSnapshotModel,
                SourceHealthSnapshotModel.source_id == BookSourceModel.id,
            )
            .outerjoin(SourceHealthProbeLeaseModel, active_lease)
            .filter(BookSourceModel.enabled == True)
            .filter(SourceHealthProbeLeaseModel.source_id.is_(None))
            .filter(
                or_(
                    SourceHealthSnapshotModel.source_id.is_(None),
                    SourceHealthSnapshotModel.next_probe_at.is_(None),
                    SourceHealthSnapshotModel.next_probe_at <= now,
                )
            )
            .order_by(
                unprobed_first.asc(),
                no_probe_time_first.asc(),
                SourceHealthSnapshotModel.last_probe_at.asc(),
                BookSourceModel.id.asc(),
            )
        )
        if limit is not None:
            query = query.limit(limit)
        return [int(row[0]) for row in query.all()]

    def release_probe_claims(
        self,
        source_ids: list[int],
        *,
        worker_id: str,
        lease_tokens: dict[int, str] | None = None,
    ) -> None:
        normalized_ids = [int(source_id) for source_id in source_ids or []]
        if not normalized_ids:
            return
        db = self._db()
        try:
            for source_id in normalized_ids:
                query = db.query(SourceHealthProbeLeaseModel).filter(
                    SourceHealthProbeLeaseModel.source_id == source_id,
                    SourceHealthProbeLeaseModel.worker_id == str(worker_id),
                )
                token = (lease_tokens or {}).get(source_id)
                if token:
                    query = query.filter(SourceHealthProbeLeaseModel.lease_token == str(token))
                query.delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            self._close(db)
