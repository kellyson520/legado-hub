from dataclasses import replace
from datetime import datetime, timedelta, timezone


def _repositories(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ai-authorization.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.ai_authorization_repo_impl import SQLiteAIAuthorizationRepository

    bootstrap_sqlite()
    return SQLiteAIAuthorizationRepository()


def _request(now=None):
    from app.domain.entities.ai_authorization import AIConversationAuthorizationRequest

    created_at = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return AIConversationAuthorizationRequest(
        id="authorization-1",
        actor_id="7",
        conversation_id="conversation-1",
        message_id="message-1",
        requested_tools=["source.search", "chapter.fetch"],
        requested_calls=[{"name": "source.search", "arguments": {"keyword": "剑来"}}],
        purpose="读取原文后再分析",
        continuation={"messages": [{"role": "user", "content": "分析"}]},
        expires_at=created_at + timedelta(minutes=15),
        created_at=created_at,
    )


def test_authorization_request_round_trip_is_scoped_to_owner(tmp_path, monkeypatch):
    repo = _repositories(tmp_path, monkeypatch)
    saved = repo.create_request(_request())

    owned = repo.get_request(saved.id, actor_id="7", conversation_id="conversation-1")

    assert owned is not None
    assert owned.requested_tools == ["source.search", "chapter.fetch"]
    assert owned.continuation["messages"][0]["content"] == "分析"
    assert repo.get_request(saved.id, actor_id="8", conversation_id="conversation-1") is None


def test_claim_pending_authorization_is_atomic(tmp_path, monkeypatch):
    repo = _repositories(tmp_path, monkeypatch)
    repo.create_request(_request())

    first = repo.claim_request("authorization-1", actor_id="7", conversation_id="conversation-1", decision="once")
    second = repo.claim_request("authorization-1", actor_id="7", conversation_id="conversation-1", decision="once")

    assert first is not None
    assert first.status == "processing"
    assert first.decision == "once"
    assert second is None


def test_claim_lease_can_only_be_renewed_by_current_owner(tmp_path, monkeypatch):
    repo = _repositories(tmp_path, monkeypatch)
    repo.create_request(_request())
    claimed = repo.claim_request("authorization-1", actor_id="7", conversation_id="conversation-1", decision="once")

    assert claimed is not None
    assert repo.renew_claim("authorization-1", "7", "wrong-token") is None
    renewed = repo.renew_claim("authorization-1", "7", claimed.claim_token)

    assert renewed is not None
    assert renewed.claim_token == claimed.claim_token
    assert renewed.claim_expires_at > claimed.claim_expires_at


def test_expired_processing_claim_is_released_for_recovery(tmp_path, monkeypatch):
    repo = _repositories(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale = replace(
        _request(now),
        status="processing",
        decision="once",
        claim_token="stale-token",
        claim_expires_at=now - timedelta(seconds=1),
    )
    repo.create_request(stale)

    assert repo.get_active_request("7", "conversation-1") is None
    assert repo.get_request(stale.id, "7", "conversation-1").status == "expired"


def test_expired_claim_cannot_be_finalized_by_old_owner(tmp_path, monkeypatch):
    repo = _repositories(tmp_path, monkeypatch)
    repo.create_request(_request())
    claimed = repo.claim_request("authorization-1", actor_id="7", conversation_id="conversation-1", decision="once")

    from app.infrastructure.persistence.sqlite.session import SessionLocal
    from app.infrastructure.persistence.sqlite.schema import AIConversationAuthorizationRequestModel

    db = SessionLocal()
    try:
        db.query(AIConversationAuthorizationRequestModel).filter_by(id="authorization-1").update({"claim_expires_at": datetime.utcnow() - timedelta(seconds=1)})
        db.commit()
    finally:
        db.close()

    assert repo.finalize_request("authorization-1", "7", "consumed", claim_token=claimed.claim_token) is None


def test_expired_pending_request_cannot_be_claimed(tmp_path, monkeypatch):
    repo = _repositories(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    repo.create_request(replace(_request(now), expires_at=now - timedelta(seconds=1)))

    assert repo.claim_request("authorization-1", "7", "conversation-1", "once") is None
    assert repo.get_request("authorization-1", "7", "conversation-1").status == "expired"


def test_duplicate_active_request_returns_existing_request(tmp_path, monkeypatch):
    repo = _repositories(tmp_path, monkeypatch)
    first = repo.create_request(_request())
    duplicate = repo.create_request(replace(_request(), id="authorization-2"))

    assert duplicate.id == first.id
    assert repo.list_requests("7", "conversation-1", status="pending") == [first]


def test_grant_can_be_listed_and_revoked(tmp_path, monkeypatch):
    repo = _repositories(tmp_path, monkeypatch)
    from app.domain.entities.ai_authorization import AIConversationAuthorizationGrant

    grant = repo.create_grant(
        AIConversationAuthorizationGrant(
            id="grant-1",
            actor_id="7",
            conversation_id="conversation-1",
            scope="conversation",
            tool_names=["source.search", "toc.get", "chapter.fetch"],
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
        )
    )

    active = repo.list_active_grants("7", "conversation-1")
    revoked = repo.revoke_grant(grant.id, actor_id="7")

    assert [item.id for item in active] == ["grant-1"]
    assert revoked is not None
    assert repo.list_active_grants("7", "conversation-1") == []


def test_expired_grant_is_not_active(tmp_path, monkeypatch):
    repo = _repositories(tmp_path, monkeypatch)
    from app.domain.entities.ai_authorization import AIConversationAuthorizationGrant

    repo.create_grant(
        AIConversationAuthorizationGrant(
            id="grant-expired",
            actor_id="7",
            conversation_id="conversation-1",
            scope="conversation",
            tool_names=["chapter.fetch"],
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1),
        )
    )

    assert repo.list_active_grants("7", "conversation-1") == []


def test_duplicate_active_grant_returns_existing_grant(tmp_path, monkeypatch):
    repo = _repositories(tmp_path, monkeypatch)
    from app.domain.entities.ai_authorization import AIConversationAuthorizationGrant

    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    first = repo.create_grant(
        AIConversationAuthorizationGrant(
            id="grant-1",
            actor_id="7",
            conversation_id="conversation-1",
            scope="conversation",
            tool_names=["source.search"],
            expires_at=expires_at,
        )
    )
    duplicate = repo.create_grant(
        AIConversationAuthorizationGrant(
            id="grant-2",
            actor_id="7",
            conversation_id="conversation-1",
            scope="conversation",
            tool_names=["source.search", "chapter.fetch"],
            expires_at=expires_at,
        )
    )

    assert duplicate.id == first.id
    assert repo.list_active_grants("7", "conversation-1")[0].tool_names == ["chapter.fetch", "source.search"]
