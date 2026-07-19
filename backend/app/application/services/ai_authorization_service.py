import json
from datetime import datetime, timedelta
from uuid import uuid4

from app.core.redaction import sanitize_for_boundary
from app.domain.entities.ai_authorization import (
    AIConversationAuthorizationGrant,
    AIConversationAuthorizationRequest,
)
from app.domain.entities.auth import AuditEvent
from app.core.exceptions import NotFoundException, ValidationException


CONTENT_TOOLS = frozenset({"source.search", "toc.get", "chapter.fetch"})
DECISIONS = frozenset({"once", "conversation", "remember", "deny"})
CHOICES = ["once", "conversation", "remember", "deny"]
PURPOSES = {
    "chat": "读取书源原文以便基于证据回答问题",
    "character": "读取书源原文以便基于证据分析人物",
    "storyline": "读取书源原文以便基于证据梳理剧情",
    "world": "读取书源原文以便基于证据分析世界观",
}
REQUEST_TTL = timedelta(minutes=15)
CONVERSATION_GRANT_TTL = timedelta(hours=24)
REMEMBERED_GRANT_TTL = timedelta(days=30)
MAX_CONTINUATION_BYTES = 128 * 1024


class AIConversationAuthorizationService:
    def __init__(self, *, repo, audit):
        self._repo = repo
        self._audit = audit

    async def create_request(
        self,
        *,
        actor_id: str,
        conversation_id: str,
        message_id: str,
        mode: str,
        requested_tools: list[str],
        requested_calls: list[dict],
        continuation: dict,
    ) -> dict:
        tools = list(dict.fromkeys(str(name) for name in requested_tools))
        if not tools or any(name not in CONTENT_TOOLS for name in tools):
            raise ValueError("Only content retrieval tools can require authorization")
        safe_calls = sanitize_for_boundary(requested_calls)
        safe_continuation = sanitize_for_boundary(continuation)
        encoded = json.dumps(safe_continuation, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_CONTINUATION_BYTES:
            raise ValidationException("AI authorization continuation is too large")
        now = datetime.utcnow()
        request = AIConversationAuthorizationRequest(
            id=uuid4().hex,
            actor_id=str(actor_id),
            conversation_id=str(conversation_id),
            message_id=str(message_id),
            requested_tools=tools,
            requested_calls=safe_calls if isinstance(safe_calls, list) else [],
            purpose=PURPOSES.get(mode, PURPOSES["chat"]),
            continuation=safe_continuation if isinstance(safe_continuation, dict) else {},
            expires_at=now + REQUEST_TTL,
            created_at=now,
            updated_at=now,
        )
        saved = self._repo.create_request(request)
        await self._audit_event(actor_id, "ai.authorization.requested", saved.id)
        return self.serialize_request(saved)

    async def decide(self, request_id: str, *, actor_id: str, conversation_id: str, decision: str) -> dict:
        if decision not in DECISIONS:
            raise ValidationException("Invalid authorization decision")
        request = self._repo.get_request(request_id, str(actor_id), str(conversation_id))
        if request is None:
            raise NotFoundException("AI authorization request not found")
        if request.status == "pending" and request.expires_at and request.expires_at <= datetime.utcnow():
            expired = self._repo.expire_request(request_id, str(actor_id), str(conversation_id))
            if expired is not None:
                await self._audit_event(actor_id, "ai.authorization.expired", request_id)
            request = expired or request
        if request.status != "pending":
            return self.serialize_request(request)

        claimed = self._repo.claim_request(request_id, str(actor_id), str(conversation_id), decision)
        if claimed is None:
            current = self._repo.get_request(request_id, str(actor_id), str(conversation_id))
            return self.serialize_request(current) if current is not None else {"id": request_id, "status": "expired"}
        if decision == "deny":
            denied = self._repo.finalize_request(request_id, str(actor_id), "denied") or claimed
            await self._audit_event(actor_id, "ai.authorization.denied", request_id)
            return self.serialize_request(denied)

        if decision in {"conversation", "remember"}:
            scope = "conversation" if decision == "conversation" else "remembered"
            conversation_scope = str(conversation_id) if scope == "conversation" else None
            existing = next(
                (
                    grant for grant in self._repo.list_active_grants(str(actor_id), conversation_scope)
                    if grant.scope == scope and set(grant.tool_names) >= set(claimed.requested_tools)
                ),
                None,
            )
            if existing is None:
                ttl = CONVERSATION_GRANT_TTL if scope == "conversation" else REMEMBERED_GRANT_TTL
                now = datetime.utcnow()
                self._repo.create_grant(
                    AIConversationAuthorizationGrant(
                        id=uuid4().hex,
                        actor_id=str(actor_id),
                        conversation_id=conversation_scope,
                        scope=scope,
                        tool_names=claimed.requested_tools,
                        expires_at=now + ttl,
                        created_at=now,
                        updated_at=now,
                    )
                )
        await self._audit_event(actor_id, f"ai.authorization.approved_{decision}", request_id)
        return self.serialize_request(claimed)

    async def finalize(self, request_id: str, *, actor_id: str, status: str, result_message_id: str | None = None) -> dict:
        if status not in {"consumed", "failed"}:
            raise ValidationException("Invalid authorization final status")
        request = self._repo.finalize_request(
            request_id,
            str(actor_id),
            status,
            result_message_id=result_message_id,
        )
        if request is None:
            request = self._repo.get_request(request_id, str(actor_id))
        if request is None:
            raise NotFoundException("AI authorization request not found")
        await self._audit_event(actor_id, f"ai.authorization.{status}", request_id)
        return self.serialize_request(request)

    def list_pending(self, actor_id: str, conversation_id: str) -> list[dict]:
        now = datetime.utcnow()
        rows = self._repo.list_requests(str(actor_id), str(conversation_id), status="pending")
        result = []
        for request in rows:
            if request.expires_at and request.expires_at <= now:
                self._repo.expire_request(request.id, str(actor_id), str(conversation_id))
                continue
            result.append(self.serialize_request(request))
        return result

    def list_grants(self, actor_id: str, conversation_id: str | None = None) -> list[dict]:
        return [self.serialize_grant(grant) for grant in self._repo.list_active_grants(str(actor_id), conversation_id)]

    async def revoke_grant(self, grant_id: str, *, actor_id: str) -> dict:
        grant = self._repo.revoke_grant(grant_id, str(actor_id))
        if grant is None:
            raise NotFoundException("AI authorization grant not found")
        await self._audit_event(actor_id, "ai.authorization.revoked", grant_id)
        return self.serialize_grant(grant)

    def active_tool_names(self, actor_id: str, conversation_id: str, rbac_permissions: set[str]) -> set[str]:
        if "book_sources.read" not in set(rbac_permissions):
            return set()
        names: set[str] = set()
        for grant in self._repo.list_active_grants(str(actor_id), str(conversation_id)):
            names.update(set(grant.tool_names) & CONTENT_TOOLS)
        return names

    @staticmethod
    def serialize_request(request: AIConversationAuthorizationRequest) -> dict:
        return {
            "id": request.id,
            "conversation_id": request.conversation_id,
            "tools": list(request.requested_tools),
            "purpose": request.purpose,
            "status": request.status,
            "decision": request.decision,
            "expires_at": request.expires_at.isoformat() if request.expires_at else None,
            "resolved_at": request.resolved_at.isoformat() if request.resolved_at else None,
            "result_message_id": request.result_message_id,
            "choices": CHOICES if request.status == "pending" else [],
        }

    @staticmethod
    def serialize_grant(grant: AIConversationAuthorizationGrant) -> dict:
        return {
            "id": grant.id,
            "scope": grant.scope,
            "conversation_id": grant.conversation_id,
            "tools": list(grant.tool_names),
            "expires_at": grant.expires_at.isoformat(),
            "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
        }

    async def _audit_event(self, actor_id: str, action: str, resource: str) -> None:
        await self._audit.record_audit(
            AuditEvent(actor_id=int(actor_id), action=action, resource="ai_authorization", detail=str(resource))
        )
