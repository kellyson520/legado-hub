import json
from datetime import timezone

from sqlalchemy import or_

from app.database import SessionLocal
from app.domain.entities.event_delivery import EventDelivery, EventDeliveryAttempt
from app.domain.repositories.event_delivery_repo import EventDeliveryRepository

from .schema import EventDeliveryAttemptModel, EventDeliveryModel


class SQLiteEventDeliveryRepository(EventDeliveryRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    @staticmethod
    def _utc(value):
        return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value

    @classmethod
    def _entity(cls, model: EventDeliveryModel) -> EventDelivery:
        return EventDelivery(
            event_id=model.event_id,
            event_type=model.event_type,
            tenant_id=model.tenant_id,
            target_url=model.target_url,
            body=model.body,
            headers=json.loads(model.headers_json or '{}'),
            dedupe_key=model.dedupe_key,
            status=model.status,
            attempt_count=model.attempt_count,
            last_error=model.last_error,
            next_attempt_at=cls._utc(model.next_attempt_at),
            delivered_at=cls._utc(model.delivered_at),
            created_at=cls._utc(model.created_at),
        )

    @classmethod
    def _attempt_entity(cls, model: EventDeliveryAttemptModel) -> EventDeliveryAttempt:
        return EventDeliveryAttempt(
            id=model.id,
            event_id=model.event_id,
            attempt_no=model.attempt_no,
            delivered=model.delivered,
            status_code=model.status_code,
            error_message=model.error_message,
            created_at=cls._utc(model.created_at),
        )

    def get(self, event_id: str) -> EventDelivery | None:
        db = self._db()
        try:
            model = db.query(EventDeliveryModel).filter(EventDeliveryModel.event_id == event_id).first()
            return self._entity(model) if model else None
        finally:
            self._close(db)

    def get_by_dedupe_key(self, tenant_id: str, dedupe_key: str) -> EventDelivery | None:
        db = self._db()
        try:
            model = (
                db.query(EventDeliveryModel)
                .filter(
                    EventDeliveryModel.tenant_id == tenant_id,
                    EventDeliveryModel.dedupe_key == dedupe_key,
                )
                .first()
            )
            return self._entity(model) if model else None
        finally:
            self._close(db)

    def list_due(self, *, now, limit: int = 20) -> list[EventDelivery]:
        db = self._db()
        try:
            models = (
                db.query(EventDeliveryModel)
                .filter(
                    EventDeliveryModel.status.in_(('pending', 'retrying')),
                    or_(
                        EventDeliveryModel.next_attempt_at.is_(None),
                        EventDeliveryModel.next_attempt_at <= now,
                    ),
                )
                .order_by(EventDeliveryModel.created_at.asc(), EventDeliveryModel.event_id.asc())
                .limit(limit)
                .all()
            )
            return [self._entity(model) for model in models]
        finally:
            self._close(db)

    def list_deliveries(self, limit: int = 50) -> list[EventDelivery]:
        db = self._db()
        try:
            models = (
                db.query(EventDeliveryModel)
                .order_by(EventDeliveryModel.created_at.desc(), EventDeliveryModel.event_id.desc())
                .limit(limit)
                .all()
            )
            return [self._entity(model) for model in models]
        finally:
            self._close(db)

    def list_deliveries_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
    ) -> tuple[list[EventDelivery], int]:
        db = self._db()
        try:
            query = db.query(EventDeliveryModel)
            if status:
                query = query.filter(EventDeliveryModel.status == status)
            normalized_search = search.strip()
            if normalized_search:
                pattern = f"%{normalized_search}%"
                query = query.filter(
                    or_(
                        EventDeliveryModel.event_id.ilike(pattern),
                        EventDeliveryModel.event_type.ilike(pattern),
                        EventDeliveryModel.tenant_id.ilike(pattern),
                        EventDeliveryModel.target_url.ilike(pattern),
                    )
                )
            total = query.count()
            models = (
                query.order_by(EventDeliveryModel.created_at.desc(), EventDeliveryModel.event_id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return [self._entity(model) for model in models], total
        finally:
            self._close(db)

    def save(self, delivery: EventDelivery) -> EventDelivery:
        db = self._db()
        try:
            model = EventDeliveryModel(
                event_id=delivery.event_id,
                event_type=delivery.event_type,
                tenant_id=delivery.tenant_id,
                target_url=delivery.target_url,
                body=delivery.body,
                headers_json=json.dumps(delivery.headers, ensure_ascii=False),
                dedupe_key=delivery.dedupe_key,
                status=delivery.status,
                attempt_count=delivery.attempt_count,
                last_error=delivery.last_error,
                next_attempt_at=delivery.next_attempt_at,
                delivered_at=delivery.delivered_at,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._entity(model)
        finally:
            self._close(db)

    def record_attempt(
        self,
        *,
        event_id: str,
        attempt: EventDeliveryAttempt,
        status: str,
        attempt_count: int,
        last_error: str | None,
        next_attempt_at,
        delivered_at,
    ) -> EventDelivery:
        db = self._db()
        try:
            model = db.query(EventDeliveryModel).filter(EventDeliveryModel.event_id == event_id).first()
            if model is None:
                raise KeyError(event_id)
            db.add(
                EventDeliveryAttemptModel(
                    event_id=event_id,
                    attempt_no=attempt.attempt_no,
                    delivered=attempt.delivered,
                    status_code=attempt.status_code,
                    error_message=attempt.error_message,
                    created_at=attempt.created_at,
                )
            )
            model.status = status
            model.attempt_count = attempt_count
            model.last_error = last_error
            model.next_attempt_at = next_attempt_at
            model.delivered_at = delivered_at
            db.commit()
            db.refresh(model)
            return self._entity(model)
        finally:
            self._close(db)

    def list_attempts(self, event_id: str) -> list[EventDeliveryAttempt]:
        db = self._db()
        try:
            rows = (
                db.query(EventDeliveryAttemptModel)
                .filter(EventDeliveryAttemptModel.event_id == event_id)
                .order_by(EventDeliveryAttemptModel.attempt_no.asc(), EventDeliveryAttemptModel.id.asc())
                .all()
            )
            return [self._attempt_entity(row) for row in rows]
        finally:
            self._close(db)
