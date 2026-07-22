from datetime import datetime, timedelta, timezone


def test_utc_iso_treats_naive_history_as_utc_and_marks_it_with_z():
    from app.core.time import to_utc_iso

    assert to_utc_iso(datetime(2026, 7, 22, 8, 30, 0)) == "2026-07-22T08:30:00Z"


def test_utc_iso_preserves_the_instant_of_aware_history():
    from app.core.time import to_utc_iso

    value = datetime(2026, 7, 22, 16, 30, 0, tzinfo=timezone(timedelta(hours=8)))

    assert to_utc_iso(value) == "2026-07-22T08:30:00Z"


def test_ai_serializers_normalize_legacy_naive_datetimes():
    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.application.services.novel_agent_app_service import NovelAgentAppService
    from app.domain.entities.ai_conversation import AIConversation, AIConversationMessage

    conversation = AIConversation(id="c1", actor_id="1", title="历史", created_at=datetime(2026, 7, 22, 8, 30))
    message = AIConversationMessage(
        id="m1",
        conversation_id="c1",
        role="assistant",
        mode="chat",
        content="回答",
        created_at=datetime(2026, 7, 22, 8, 31),
    )

    assert AIWorkspaceService._serialize_conversation(conversation)["created_at"].endswith("Z")
    assert AIWorkspaceService._serialize_message(message)["created_at"].endswith("Z")
    assert NovelAgentAppService._serialize_conversation(conversation, messages=[message])["created_at"].endswith("Z")
    assert NovelAgentAppService._serialize_message(message)["created_at"].endswith("Z")
