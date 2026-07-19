import json
from datetime import datetime

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
                created_at=request.created_at,
                updated_at=request.updated_at,
            )
            db.add(model)
            db.commit()
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
            updated = (
                db.query(AIConversationAuthorizationRequestModel)
                .filter(
                    AIConversationAuthorizationRequestModel.id == request_id,
                    AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
                    AIConversationAuthorizationRequestModel.conversation_id == conversation_id,
                    AIConversationAuthorizationRequestModel.status == "pending",
                    AIConversationAuthorizationRequestModel.expires_at > now,
                )
                .update({"status": "processing", "decision": decision, "updated_at": now}, synchronize_session=False)
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

    def finalize_request(self, request_id: str, actor_id: str, status: str, *, result_message_id: str | None = None) -> AIConversationAuthorizationRequest | None:
        db = self._db()
        try:
            now = datetime.utcnow()
            updated = (
                db.query(AIConversationAuthorizationRequestModel)
                .filter(
                    AIConversationAuthorizationRequestModel.id == request_id,
                    AIConversationAuthorizationRequestModel.actor_id == str(actor_id),
                    AIConversationAuthorizationRequestModel.status == "processing",
                )
                .update({"status": status, "resolved_at": now, "resolved_by": str(actor_id), "result_message_id": result_message_id, "updated_at": now}, synchronize_session=False)
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
                    AIConversationAuthorizationRequestModel.status == "pending",
                )
                .update({"status": "expired", "resolved_at": now, "resolved_by": str(actor_id), "updated_at": now}, synchronize_session=False)
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
            db.commit()
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
            created_at=model.created_at,
            updated_at=model.updated_at,
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
