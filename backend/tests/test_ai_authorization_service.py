from datetime import datetime, timedelta, timezone

import pytest


class Audit:
    def __init__(self):
        self.events = []

    async def record_audit(self, event):
        self.events.append(event)


class Repo:
    def __init__(self):
        self.requests = {}
        self.grants = {}

    def create_request(self, request):
        self.requests[request.id] = request
        return request

    def get_request(self, request_id, actor_id, conversation_id=None):
        request = self.requests.get(request_id)
        if request is None or request.actor_id != str(actor_id) or (conversation_id is not None and request.conversation_id != conversation_id):
            return None
        return request

    def list_requests(self, actor_id, conversation_id, status=None):
        return [
            request for request in self.requests.values()
            if request.actor_id == str(actor_id)
            and request.conversation_id == conversation_id
            and (status is None or request.status == status)
        ]

    def claim_request(self, request_id, actor_id, conversation_id, decision):
        request = self.get_request(request_id, actor_id, conversation_id)
        if request is None or request.status != "pending":
            return None
        request.status = "processing"
        request.decision = decision
        return request

    def finalize_request(self, request_id, actor_id, status, *, result_message_id=None):
        request = self.get_request(request_id, actor_id)
        if request is None or request.status != "processing":
            return None
        request.status = status
        request.result_message_id = result_message_id
        request.resolved_at = datetime.utcnow()
        request.resolved_by = str(actor_id)
        return request

    def expire_request(self, request_id, actor_id, conversation_id):
        request = self.get_request(request_id, actor_id, conversation_id)
        if request is None or request.status != "pending":
            return None
        request.status = "expired"
        request.resolved_at = datetime.utcnow()
        return request

    def create_grant(self, grant):
        self.grants[grant.id] = grant
        return grant

    def list_active_grants(self, actor_id, conversation_id=None):
        now = datetime.utcnow()
        return [
            grant for grant in self.grants.values()
            if grant.actor_id == str(actor_id)
            and grant.revoked_at is None
            and grant.expires_at > now
            and (conversation_id is None or grant.conversation_id in (None, conversation_id))
        ]

    def revoke_grant(self, grant_id, actor_id):
        grant = self.grants.get(grant_id)
        if grant is None or grant.actor_id != str(actor_id) or grant.revoked_at is not None:
            return None
        grant.revoked_at = datetime.utcnow()
        return grant

    def count_active_grants(self, actor_id, conversation_id):
        return len(self.list_active_grants(actor_id, conversation_id))


def _service():
    from app.application.services.ai_authorization_service import AIConversationAuthorizationService

    repo = Repo()
    audit = Audit()
    return AIConversationAuthorizationService(repo=repo, audit=audit), repo, audit


@pytest.mark.asyncio
async def test_decision_is_idempotent_and_creates_only_one_grant():
    service, repo, _ = _service()
    request = await service.create_request(
        actor_id="7",
        conversation_id="c1",
        message_id="m1",
        mode="character",
        requested_tools=["source.search"],
        requested_calls=[{"name": "source.search", "arguments": {"keyword": "剑来"}}],
        continuation={"messages": []},
    )

    first = await service.decide(request["id"], actor_id="7", conversation_id="c1", decision="conversation")
    second = await service.decide(request["id"], actor_id="7", conversation_id="c1", decision="conversation")

    assert first["status"] == second["status"] == "processing"
    assert repo.count_active_grants(actor_id="7", conversation_id="c1") == 1


@pytest.mark.asyncio
async def test_request_purpose_and_sensitive_continuation_are_fixed_and_redacted():
    service, _, _ = _service()

    request = await service.create_request(
        actor_id="7",
        conversation_id="c1",
        message_id="m1",
        mode="world",
        requested_tools=["chapter.fetch"],
        requested_calls=[{"name": "chapter.fetch", "arguments": {"cookie": "secret", "chapter_index": 1}}],
        continuation={"messages": [{"role": "user", "content": "authorization: Bearer hidden"}]},
    )

    assert request["purpose"] == "读取书源原文以便基于证据分析世界观"
    assert request["choices"] == ["once", "conversation", "remember", "deny"]
    assert "secret" not in str(request)
    assert "hidden" not in str(request)


@pytest.mark.asyncio
async def test_only_content_tools_can_create_authorization_request():
    service, _, _ = _service()

    with pytest.raises(ValueError):
        await service.create_request(
            actor_id="7",
            conversation_id="c1",
            message_id="m1",
            mode="chat",
            requested_tools=["create_source_rule_draft"],
            requested_calls=[],
            continuation={},
        )


@pytest.mark.asyncio
async def test_active_tool_names_require_rbac_and_include_conversation_and_remembered_grants():
    service, repo, _ = _service()
    from app.domain.entities.ai_authorization import AIConversationAuthorizationGrant

    now = datetime.utcnow()
    repo.create_grant(AIConversationAuthorizationGrant("g1", "7", "c1", "conversation", ["source.search"], now + timedelta(hours=1)))
    repo.create_grant(AIConversationAuthorizationGrant("g2", "7", None, "remembered", ["chapter.fetch"], now + timedelta(days=1)))

    assert service.active_tool_names("7", "c1", {"book_sources.read"}) == {"source.search", "chapter.fetch"}
    assert service.active_tool_names("7", "c1", set()) == set()
