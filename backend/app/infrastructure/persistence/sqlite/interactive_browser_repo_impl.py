import hashlib
import json
from datetime import datetime, timezone

from app.database import SessionLocal
from app.domain.entities.interactive_browser import (
    InteractiveBrowserEvent,
    InteractiveBrowserSession,
    InteractiveBrowserState,
)
from app.domain.repositories.interactive_browser_repo import InteractiveBrowserRepository

from .schema import InteractiveBrowserEventModel, InteractiveBrowserSessionModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


class SQLiteInteractiveBrowserRepository(InteractiveBrowserRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db) -> None:
        if self._session is None:
            db.close()

    @staticmethod
    def _session_entity(model: InteractiveBrowserSessionModel) -> InteractiveBrowserSession:
        allowed_origins = json.loads(model.allowed_origins or '[]')
        return InteractiveBrowserSession(
            id=model.id,
            source_version_id=model.source_version_id,
            owner_id=model.owner_id,
            allowed_origins=allowed_origins if isinstance(allowed_origins, list) else [],
            state=InteractiveBrowserState(model.state),
            automatic_attempted=bool(model.automatic_attempted),
            expires_at=model.expires_at,
            closed_at=model.closed_at,
            terminal_reason=model.terminal_reason,
            created_at=model.created_at,
        )

    @staticmethod
    def _event_entity(model: InteractiveBrowserEventModel) -> InteractiveBrowserEvent:
        detail = json.loads(model.detail or '{}')
        return InteractiveBrowserEvent(
            id=model.id,
            session_id=model.session_id,
            event_type=model.event_type,
            actor_id=model.actor_id,
            detail=detail if isinstance(detail, dict) else {},
            created_at=model.created_at,
        )

    def create(self, session: InteractiveBrowserSession) -> InteractiveBrowserSession:
        db = self._db()
        try:
            model = InteractiveBrowserSessionModel(
                id=session.id,
                source_version_id=session.source_version_id,
                owner_id=session.owner_id,
                allowed_origins=json.dumps(session.allowed_origins, ensure_ascii=False),
                state=session.state.value,
                automatic_attempted=session.automatic_attempted,
                expires_at=session.expires_at,
                closed_at=session.closed_at,
                terminal_reason=session.terminal_reason,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._session_entity(model)
        finally:
            self._close(db)

    def get(self, session_id: str) -> InteractiveBrowserSession | None:
        db = self._db()
        try:
            model = db.query(InteractiveBrowserSessionModel).filter(
                InteractiveBrowserSessionModel.id == session_id,
            ).first()
            return self._session_entity(model) if model is not None else None
        finally:
            self._close(db)

    def get_for_owner(self, session_id: str, owner_id: str) -> InteractiveBrowserSession | None:
        db = self._db()
        try:
            model = db.query(InteractiveBrowserSessionModel).filter(
                InteractiveBrowserSessionModel.id == session_id,
                InteractiveBrowserSessionModel.owner_id == owner_id,
            ).first()
            return self._session_entity(model) if model is not None else None
        finally:
            self._close(db)

    def find_active_for_source(self, source_version_id: str, owner_id: str) -> InteractiveBrowserSession | None:
        db = self._db()
        try:
            states = (
                InteractiveBrowserState.PENDING.value,
                InteractiveBrowserState.AUTOMATIC_RUNNING.value,
                InteractiveBrowserState.AWAITING_MANUAL.value,
                InteractiveBrowserState.VALIDATING.value,
            )
            model = db.query(InteractiveBrowserSessionModel).filter(
                InteractiveBrowserSessionModel.source_version_id == source_version_id,
                InteractiveBrowserSessionModel.owner_id == owner_id,
                InteractiveBrowserSessionModel.state.in_(states),
            ).order_by(InteractiveBrowserSessionModel.created_at.desc()).first()
            return self._session_entity(model) if model is not None else None
        finally:
            self._close(db)

    def update_state(
        self,
        session_id: str,
        *,
        state: InteractiveBrowserState,
        automatic_attempted: bool | None = None,
        terminal_reason: str | None = None,
        closed_at: datetime | None = None,
    ) -> InteractiveBrowserSession:
        db = self._db()
        try:
            model = db.query(InteractiveBrowserSessionModel).filter(
                InteractiveBrowserSessionModel.id == session_id,
            ).first()
            if model is None:
                raise KeyError(session_id)
            model.state = state.value
            if automatic_attempted is not None:
                model.automatic_attempted = automatic_attempted
            if terminal_reason is not None:
                model.terminal_reason = terminal_reason
            if closed_at is not None:
                model.closed_at = closed_at.replace(tzinfo=None) if closed_at.tzinfo else closed_at
            db.commit()
            db.refresh(model)
            return self._session_entity(model)
        finally:
            self._close(db)

    def count_active(self) -> int:
        db = self._db()
        try:
            states = (
                InteractiveBrowserState.PENDING.value,
                InteractiveBrowserState.AUTOMATIC_RUNNING.value,
                InteractiveBrowserState.AWAITING_MANUAL.value,
                InteractiveBrowserState.VALIDATING.value,
            )
            return int(db.query(InteractiveBrowserSessionModel).filter(
                InteractiveBrowserSessionModel.state.in_(states),
            ).count())
        finally:
            self._close(db)

    def issue_relay_token(
        self,
        *,
        session_id: str,
        owner_id: str,
        raw_token: str,
        expires_at: datetime,
    ) -> None:
        db = self._db()
        try:
            model = db.query(InteractiveBrowserSessionModel).filter(
                InteractiveBrowserSessionModel.id == session_id,
                InteractiveBrowserSessionModel.owner_id == owner_id,
            ).first()
            if model is None:
                raise KeyError(session_id)
            model.relay_token_digest = _token_digest(raw_token)
            model.relay_token_owner_id = owner_id
            model.relay_token_expires_at = expires_at.replace(tzinfo=None) if expires_at.tzinfo else expires_at
            model.relay_token_consumed_at = None
            db.commit()
        finally:
            self._close(db)

    def consume_relay_token(self, raw_token: str, *, owner_id: str) -> InteractiveBrowserSession | None:
        db = self._db()
        try:
            model = db.query(InteractiveBrowserSessionModel).filter(
                InteractiveBrowserSessionModel.relay_token_digest == _token_digest(raw_token),
                InteractiveBrowserSessionModel.relay_token_owner_id == owner_id,
                InteractiveBrowserSessionModel.relay_token_consumed_at.is_(None),
            ).first()
            if model is None or model.relay_token_expires_at is None or model.relay_token_expires_at <= _utcnow():
                return None
            model.relay_token_consumed_at = _utcnow()
            db.commit()
            db.refresh(model)
            return self._session_entity(model)
        finally:
            self._close(db)

    def record_event(
        self,
        *,
        session_id: str,
        event_type: str,
        actor_id: str,
        detail: dict,
    ) -> InteractiveBrowserEvent:
        db = self._db()
        try:
            model = InteractiveBrowserEventModel(
                session_id=session_id,
                event_type=event_type,
                actor_id=actor_id,
                detail=json.dumps(detail, ensure_ascii=False),
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._event_entity(model)
        finally:
            self._close(db)
