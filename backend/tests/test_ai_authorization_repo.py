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
