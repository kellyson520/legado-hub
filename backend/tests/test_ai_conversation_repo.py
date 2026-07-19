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
