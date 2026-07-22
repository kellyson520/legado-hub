from datetime import datetime, timedelta


def test_conversation_repository_persists_messages_and_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ai-conversations.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.domain.entities.ai_conversation import AIConversation, AIConversationMessage
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = SQLiteAIConversationRepository()
    repo.create_conversation(AIConversation(id="conversation-1", actor_id="7", title="人物介绍"))
    repo.append_message(
        AIConversationMessage(
            id="message-1",
            conversation_id="conversation-1",
            role="user",
            mode="character",
            content="介绍主角",
            metadata={"authorization_request_id": "auth-1"},
        )
    )

    owned = repo.get_conversation("conversation-1", "7")

    assert owned is not None
    assert owned.title == "人物介绍"
    assert repo.get_conversation("conversation-1", "8") is None
    messages = repo.list_messages("conversation-1")
    assert [item.content for item in messages] == ["介绍主角"]
    assert messages[0].metadata == {"authorization_request_id": "auth-1"}


def test_conversation_repository_lists_only_recent_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "recent-ai-conversations.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.domain.entities.ai_conversation import AIConversation, AIConversationMessage
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = SQLiteAIConversationRepository()
    repo.create_conversation(AIConversation(id="conversation-recent", actor_id="7", title="历史"))
    base_time = datetime(2026, 7, 22, 8, 0, 0)
    for index in range(4):
        repo.append_message(
            AIConversationMessage(
                id=f"message-{index}",
                conversation_id="conversation-recent",
                role="user",
                mode="chat",
                content=f"问题 {index}",
                created_at=base_time + timedelta(seconds=index),
            )
        )

    recent = repo.list_recent_messages("conversation-recent", limit=2)

    assert [item.content for item in recent] == ["问题 2", "问题 3"]
