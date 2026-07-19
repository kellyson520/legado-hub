import json
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from app.domain.entities.ai_authorization import (
    AIConversationAuthorizationGrant,
    AIConversationAuthorizationRequest,
)
from app.domain.repositories.ai_authorization_repo import AIAuthorizationRepository
from app.infrastructure.persistence.sqlite.session import SessionLocal

from .schema import AIConversationAuthorizationGrantModel, AIConversationAuthorizationRequestModel


class SQLiteAIAuthorizationRepository(AIAuthorizationRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db) -> None:
        if self._session is None:
            db.close()

    def create_request(self, request: AIConversationAuthorizationRequest) -> AIConversationAuthorizationRequest:
        db = self._db()
        try:
            model = AIConversationAuthorizationRequestModel(
                id=request.id,
                actor_id=request.actor_id,
                conversation_id=request.conversation_id,
                message_id=request.message_id,
                requested_tools=json.dumps(request.requested_tools, ensure_ascii=False),
                requested_calls=json.dumps(request.requested_calls, ensure_ascii=False),
                purpose=request.purpose,
                continuation=json.dumps(request.continuation, ensure_ascii=False),
                status=request.status,
                decision=request.decision,
                expires_at=request.expires_at,
                resolved_at=request.resolved_at,
                resolved_by=request.resolved_by,
                result_message_id=request.result_message_id,
                claim_token=request.claim_token,
                claim_expires_at=request.claim_expires_at,
                created_at=request.created_at,
                updated_at=request.updated_at,
            )
            db.add(model)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                query = db.query(AIConversationAuthorizationRequestModel).filter(
                    AIConversationAuthorizationRequestModel.actor_id == str(request.actor_id),
                    AIConversationAuthorizationRequestModel.conversation_id == str(request.conversation_id),
                    AIConversationAuthorizationRequestModel.status.in_(("pending", "processing")),
                )
                existing = query.order_by(
                    AIConversationAuthorizationRequestModel.created_at.desc(),
                    AIConversationAuthorizationRequestModel.id.desc(),
                ).first()
                if existing is None:
                    raise
                return self._request(existing)
            db.refresh(model)
            return self._request(model)
        finally:
            self._close(db)

    def get_request(self, request_id: str, actor_id: str, conversation_id: str | None = None) -> AIConversationAuthorizationRequest | None:
        db = self._db()
        try:
            query = db.query(AIConversationAuthorizationRequestModel).filter(
                AIConversationAuthorizationRequestModel.id == request_id,
                AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
            )
            if conversation_id is not None:
                query = query.filter(AIConversationAuthorizationRequestModel.conversation_id == conversation_id)
            row = query.first()
            return self._request(row) if row is not None else None
        finally:
            self._close(db)

    def get_active_request(self, actor_id: str, conversation_id: str) -> AIConversationAuthorizationRequest | None:
        db = self._db()
        try:
            now = datetime.utcnow()
            stale = db.query(AIConversationAuthorizationRequestModel).filter(
                AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
                AIConversationAuthorizationRequestModel.conversation_id == str(conversation_id),
                or_(
                    and_(
                        AIConversationAuthorizationRequestModel.status == "pending",
                        AIConversationAuthorizationRequestModel.expires_at <= now,
                    ),
                    and_(
                        AIConversationAuthorizationRequestModel.status == "processing",
                        or_(
                            AIConversationAuthorizationRequestModel.expires_at <= now,
                            AIConversationAuthorizationRequestModel.claim_expires_at <= now,
                            AIConversationAuthorizationRequestModel.claim_expires_at.is_(None),
                        ),
                    ),
                ),
            ).update(self._expired_values(now, str(actor_id)), synchronize_session=False)
            if stale:
                db.commit()
            row = db.query(AIConversationAuthorizationRequestModel).filter(
                AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
                AIConversationAuthorizationRequestModel.conversation_id == str(conversation_id),
                or_(
                    and_(
                        AIConversationAuthorizationRequestModel.status == "pending",
                        AIConversationAuthorizationRequestModel.expires_at > now,
                    ),
                    and_(
                        AIConversationAuthorizationRequestModel.status == "processing",
                        AIConversationAuthorizationRequestModel.expires_at > now,
                        AIConversationAuthorizationRequestModel.claim_expires_at > now,
                    ),
                ),
            ).order_by(AIConversationAuthorizationRequestModel.created_at.desc()).first()
            return self._request(row) if row is not None else None
        finally:
            self._close(db)

    def list_requests(self, actor_id: str, conversation_id: str, status: str | None = None) -> list[AIConversationAuthorizationRequest]:
        db = self._db()
        try:
            query = db.query(AIConversationAuthorizationRequestModel).filter(
                AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
                AIConversationAuthorizationRequestModel.conversation_id == conversation_id,
            )
            if status:
                query = query.filter(AIConversationAuthorizationRequestModel.status == status)
            rows = query.order_by(AIConversationAuthorizationRequestModel.created_at.desc()).all()
            return [self._request(row) for row in rows]
        finally:
            self._close(db)

    def claim_request(self, request_id: str, actor_id: str, conversation_id: str, decision: str) -> AIConversationAuthorizationRequest | None:
        db = self._db()
        try:
            now = datetime.utcnow()
            stale = (
                db.query(AIConversationAuthorizationRequestModel)
                .filter(
                    AIConversationAuthorizationRequestModel.id == request_id,
                    AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
                    AIConversationAuthorizationRequestModel.conversation_id == conversation_id,
                    or_(
                        and_(
                            AIConversationAuthorizationRequestModel.status == "pending",
                            AIConversationAuthorizationRequestModel.expires_at <= now,
                        ),
                        and_(
                            AIConversationAuthorizationRequestModel.status == "processing",
                            or_(
                                AIConversationAuthorizationRequestModel.expires_at <= now,
                                AIConversationAuthorizationRequestModel.claim_expires_at <= now,
                                AIConversationAuthorizationRequestModel.claim_expires_at.is_(None),
                            ),
                        ),
                    ),
                )
                .update(self._expired_values(now, str(actor_id)), synchronize_session=False)
            )
            if stale:
                db.commit()
                return None
            claim_token = uuid4().hex
            claim_expires_at = datetime.utcnow().replace(microsecond=0) + timedelta(minutes=5)
            updated = (
                db.query(AIConversationAuthorizationRequestModel)
                .filter(
                    AIConversationAuthorizationRequestModel.id == request_id,
                    AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
                    AIConversationAuthorizationRequestModel.conversation_id == conversation_id,
                    AIConversationAuthorizationRequestModel.status == "pending",
                    AIConversationAuthorizationRequestModel.expires_at > now,
                )
                .update({"status": "processing", "decision": decision, "claim_token": claim_token, "claim_expires_at": claim_expires_at, "updated_at": now}, synchronize_session=False)
            )
            if updated != 1:
                db.rollback()
                return None
            db.commit()
            row = db.query(AIConversationAuthorizationRequestModel).filter(
                AIConversationAuthorizationRequestModel.id == request_id,
            ).first()
            return self._request(row) if row is not None else None
        finally:
            self._close(db)

    def renew_claim(
        self,
        request_id: str,
        actor_id: str,
        claim_token: str,
        *,
        lease_seconds: int = 300,
    ) -> AIConversationAuthorizationRequest | None:
        db = self._db()
        try:
            now = datetime.utcnow()
            updated = (
                db.query(AIConversationAuthorizationRequestModel)
                .filter(
                    AIConversationAuthorizationRequestModel.id == request_id,
                    AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
                    AIConversationAuthorizationRequestModel.status == "processing",
                    AIConversationAuthorizationRequestModel.claim_token == claim_token,
                    AIConversationAuthorizationRequestModel.expires_at > now,
                    AIConversationAuthorizationRequestModel.claim_expires_at > now,
                )
                .update({"claim_expires_at": now + timedelta(seconds=max(30, int(lease_seconds))), "updated_at": now}, synchronize_session=False)
            )
            if updated != 1:
                db.rollback()
                return None
            db.commit()
            row = db.query(AIConversationAuthorizationRequestModel).filter(
                AIConversationAuthorizationRequestModel.id == request_id,
                AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
            ).first()
            return self._request(row) if row is not None else None
        finally:
            self._close(db)

    def finalize_request(self, request_id: str, actor_id: str, status: str, *, claim_token: str | None = None, result_message_id: str | None = None) -> AIConversationAuthorizationRequest | None:
        db = self._db()
        try:
            now = datetime.utcnow()
            query = db.query(AIConversationAuthorizationRequestModel).filter(
                AIConversationAuthorizationRequestModel.id == request_id,
                AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
                AIConversationAuthorizationRequestModel.status == "processing",
                AIConversationAuthorizationRequestModel.expires_at > now,
                AIConversationAuthorizationRequestModel.claim_expires_at > now,
            )
            if claim_token is not None:
                query = query.filter(AIConversationAuthorizationRequestModel.claim_token == claim_token)
            updated = query.update({"status": status, "resolved_at": now, "resolved_by": str(actor_id), "result_message_id": result_message_id, "claim_token": None, "claim_expires_at": None, "updated_at": now}, synchronize_session=False)
            if updated != 1:
                db.rollback()
                return None
            db.commit()
            row = db.query(AIConversationAuthorizationRequestModel).filter(
                AIConversationAuthorizationRequestModel.id == request_id,
            ).first()
            return self._request(row) if row is not None else None
        finally:
            self._close(db)

    def set_result_message_id(self, request_id: str, actor_id: str, result_message_id: str) -> AIConversationAuthorizationRequest | None:
        db = self._db()
        try:
            now = datetime.utcnow()
            updated = (
                db.query(AIConversationAuthorizationRequestModel)
                .filter(
                    AIConversationAuthorizationRequestModel.id == request_id,
                    AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
                    AIConversationAuthorizationRequestModel.status.in_(("denied", "consumed", "failed", "expired")),
                    AIConversationAuthorizationRequestModel.result_message_id.is_(None),
                )
                .update({"result_message_id": str(result_message_id), "updated_at": now}, synchronize_session=False)
            )
            if updated != 1:
                db.rollback()
                row = db.query(AIConversationAuthorizationRequestModel).filter(
                    AIConversationAuthorizationRequestModel.id == request_id,
                    AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
                ).first()
                return self._request(row) if row is not None else None
            db.commit()
            row = db.query(AIConversationAuthorizationRequestModel).filter(
                AIConversationAuthorizationRequestModel.id == request_id,
                AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
            ).first()
            return self._request(row) if row is not None else None
        finally:
            self._close(db)

    def expire_request(self, request_id: str, actor_id: str, conversation_id: str) -> AIConversationAuthorizationRequest | None:
        db = self._db()
        try:
            now = datetime.utcnow()
            updated = (
                db.query(AIConversationAuthorizationRequestModel)
                .filter(
                    AIConversationAuthorizationRequestModel.id == request_id,
                    AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
                    AIConversationAuthorizationRequestModel.conversation_id == conversation_id,
                    AIConversationAuthorizationRequestModel.status.in_(("pending", "processing")),
                )
                .update({"status": "expired", "resolved_at": now, "resolved_by": str(actor_id), "claim_token": None, "claim_expires_at": None, "updated_at": now}, synchronize_session=False)
            )
            if updated != 1:
                db.rollback()
                return None
            db.commit()
            row = db.query(AIConversationAuthorizationRequestModel).filter(AIConversationAuthorizationRequestModel.id == request_id).first()
            return self._request(row) if row is not None else None
        finally:
            self._close(db)

    def create_grant(self, grant: AIConversationAuthorizationGrant) -> AIConversationAuthorizationGrant:
        db = self._db()
        try:
            now = datetime.utcnow()
            existing = self._active_grant_query(db, grant.actor_id, grant.scope, grant.conversation_id).first()
            if existing is not None:
                if existing.expires_at > now:
                    current_tools = set(json.loads(existing.tool_names or "[]"))
                    requested_tools = set(str(name) for name in grant.tool_names)
                    if requested_tools - current_tools:
                        existing.tool_names = json.dumps(sorted(current_tools | requested_tools), ensure_ascii=False)
                        existing.updated_at = now
                        db.commit()
                    return self._grant(existing)
                existing.revoked_at = now
                existing.updated_at = now
                db.flush()
            model = AIConversationAuthorizationGrantModel(
                id=grant.id,
                actor_id=grant.actor_id,
                conversation_id=grant.conversation_id,
                scope=grant.scope,
                tool_names=json.dumps(grant.tool_names, ensure_ascii=False),
                expires_at=grant.expires_at,
                revoked_at=grant.revoked_at,
                created_at=grant.created_at,
                updated_at=grant.updated_at,
            )
            db.add(model)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                existing = self._active_grant_query(db, grant.actor_id, grant.scope, grant.conversation_id).first()
                if existing is None or existing.expires_at <= now:
                    raise
                current_tools = set(json.loads(existing.tool_names or "[]"))
                requested_tools = set(str(name) for name in grant.tool_names)
                if requested_tools - current_tools:
                    existing.tool_names = json.dumps(sorted(current_tools | requested_tools), ensure_ascii=False)
                    existing.updated_at = now
                    db.commit()
                return self._grant(existing)
            db.refresh(model)
            return self._grant(model)
        finally:
            self._close(db)

    def list_active_grants(self, actor_id: str, conversation_id: str | None = None) -> list[AIConversationAuthorizationGrant]:
        db = self._db()
        try:
            now = datetime.utcnow()
            query = db.query(AIConversationAuthorizationGrantModel).filter(
                AIConversationAuthorizationGrantModel.actor_id == str(actor_id),
                AIConversationAuthorizationGrantModel.revoked_at.is_(None),
                AIConversationAuthorizationGrantModel.expires_at > now,
            )
            if conversation_id is not None:
                query = query.filter(
                    (AIConversationAuthorizationGrantModel.conversation_id == conversation_id)
                    | (AIConversationAuthorizationGrantModel.conversation_id.is_(None))
                )
            rows = query.order_by(AIConversationAuthorizationGrantModel.created_at.desc()).all()
            return [self._grant(row) for row in rows]
        finally:
            self._close(db)

    def revoke_grant(self, grant_id: str, actor_id: str) -> AIConversationAuthorizationGrant | None:
        db = self._db()
        try:
            now = datetime.utcnow()
            updated = (
                db.query(AIConversationAuthorizationGrantModel)
                .filter(
                    AIConversationAuthorizationGrantModel.id == grant_id,
                    AIConversationAuthorizationGrantModel.actor_id == str(actor_id),
                    AIConversationAuthorizationGrantModel.revoked_at.is_(None),
                )
                .update({"revoked_at": now, "updated_at": now}, synchronize_session=False)
            )
            if updated != 1:
                db.rollback()
                return None
            db.commit()
            row = db.query(AIConversationAuthorizationGrantModel).filter(AIConversationAuthorizationGrantModel.id == grant_id).first()
            return self._grant(row) if row is not None else None
        finally:
            self._close(db)

    @staticmethod
    def _request(model: AIConversationAuthorizationRequestModel) -> AIConversationAuthorizationRequest:
        return AIConversationAuthorizationRequest(
            id=model.id,
            actor_id=model.actor_id,
            conversation_id=model.conversation_id,
            message_id=model.message_id,
            requested_tools=json.loads(model.requested_tools or "[]"),
            requested_calls=json.loads(model.requested_calls or "[]"),
            purpose=model.purpose,
            continuation=json.loads(model.continuation or "{}"),
            status=model.status,
            decision=model.decision,
            expires_at=model.expires_at,
            resolved_at=model.resolved_at,
            resolved_by=model.resolved_by,
            result_message_id=model.result_message_id,
            claim_token=model.claim_token,
            claim_expires_at=model.claim_expires_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _expired_values(now: datetime, actor_id: str) -> dict:
        return {
            "status": "expired",
            "resolved_at": now,
            "resolved_by": actor_id,
            "claim_token": None,
            "claim_expires_at": None,
            "updated_at": now,
        }

    @staticmethod
    def _active_grant_query(db, actor_id: str, scope: str, conversation_id: str | None):
        query = db.query(AIConversationAuthorizationGrantModel).filter(
            AIConversationAuthorizationGrantModel.actor_id == str(actor_id),
            AIConversationAuthorizationGrantModel.scope == scope,
            AIConversationAuthorizationGrantModel.revoked_at.is_(None),
        )
        if scope == "conversation":
            query = query.filter(AIConversationAuthorizationGrantModel.conversation_id == conversation_id)
        else:
            query = query.filter(AIConversationAuthorizationGrantModel.conversation_id.is_(None))
        return query.order_by(
            AIConversationAuthorizationGrantModel.created_at.desc(),
            AIConversationAuthorizationGrantModel.id.desc(),
        )

    @staticmethod
    def _grant(model: AIConversationAuthorizationGrantModel) -> AIConversationAuthorizationGrant:
        return AIConversationAuthorizationGrant(
            id=model.id,
            actor_id=model.actor_id,
            conversation_id=model.conversation_id,
            scope=model.scope,
            tool_names=json.loads(model.tool_names or "[]"),
            expires_at=model.expires_at,
            revoked_at=model.revoked_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
