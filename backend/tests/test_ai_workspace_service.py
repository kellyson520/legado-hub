import json

import pytest


class RecordingPlatform:
    def __init__(self):
        self.calls: list[dict] = []

    async def invoke_chat(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "provider_name": "test-provider",
            "model": "test-model",
            "output": {"text": "主角信息"},
            "usage": {"input_tokens": 3, "output_tokens": 5},
            "cost": {"total": 0.01},
        }


class SourceRepository:
    def list_recent_versions(self, **_kwargs):
        return [
            type(
                "Version",
                (),
                {
                    "id": "source-version-1",
                    "source_id": "https://example.test",
                    "status": "candidate",
                    "created_by": "7",
                    "payload": {"bookSourceName": "示例源", "bookSourceUrl": "https://example.test", "cookie": "secret"},
                },
            )()
        ]


class TaskRepository:
    def list_tasks(self):
        return []


class AuditRepository:
    def __init__(self):
        self.events = []

    async def record_audit(self, event):
        self.events.append(event)


class VisibleSourceRepository:
    def list_recent_versions(self, **_kwargs):
        return [
            type(
                "Version",
                (),
                {
                    "id": "owned-candidate",
                    "source_id": "https://owned.example",
                    "status": "candidate",
                    "created_by": "7",
                    "payload": {"bookSourceName": "owned", "bookSourceUrl": "https://owned.example"},
                },
            )(),
            type(
                "Version",
                (),
                {
                    "id": "other-candidate",
                    "source_id": "https://other.example",
                    "status": "candidate",
                    "created_by": "8",
                    "payload": {"bookSourceName": "other", "bookSourceUrl": "https://other.example"},
                },
            )(),
            type(
                "Version",
                (),
                {
                    "id": "published-source",
                    "source_id": "https://published.example",
                    "status": "published",
                    "created_by": "8",
                    "payload": {"bookSourceName": "published", "bookSourceUrl": "https://published.example"},
                },
            )(),
        ]

    def get_version(self, version_id):
        return next((item for item in self.list_recent_versions() if item.id == version_id), None)


@pytest.mark.asyncio
async def test_workspace_tool_hides_candidates_owned_by_other_users(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "workspace.sqlite3"))

    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    service = AIWorkspaceService(
        RecordingPlatform(),
        SQLiteAIConversationRepository(),
        VisibleSourceRepository(),
        TaskRepository(),
        AuditRepository(),
    )
    conversation = await service.create_conversation("7")

    reply = await service.send_message(
        conversation["id"],
        "7",
        "chat",
        "list sources",
        [{"name": "list_visible_sources", "arguments": {}}],
    )

    assert [item["id"] for item in reply["tool_calls"][0]["result"]] == ["owned-candidate", "published-source"]


@pytest.mark.asyncio
async def test_workspace_tool_does_not_expose_other_users_candidate_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "workspace.sqlite3"))

    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.core.exceptions import NotFoundException
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    service = AIWorkspaceService(
        RecordingPlatform(),
        SQLiteAIConversationRepository(),
        VisibleSourceRepository(),
        TaskRepository(),
        AuditRepository(),
    )
    conversation = await service.create_conversation("7")

    with pytest.raises(NotFoundException):
        await service.send_message(
            conversation["id"],
            "7",
            "chat",
            "show source rules",
            [{"name": "get_source_rule_summary", "arguments": {"source_version_id": "other-candidate"}}],
        )


@pytest.mark.asyncio
async def test_workspace_message_persists_reply_and_sanitizes_tool_result(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "workspace.sqlite3"))

    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    audit = AuditRepository()
    platform = RecordingPlatform()
    service = AIWorkspaceService(
        platform=platform,
        conversations=SQLiteAIConversationRepository(),
        sources=SourceRepository(),
        ai_tasks=TaskRepository(),
        audit=audit,
    )
    conversation = await service.create_conversation("7", "人物介绍")
    reply = await service.send_message(
        conversation["id"],
        "7",
        "character",
        "列出书源",
        [{"name": "list_visible_sources", "arguments": {}}],
    )

    assert reply["content"] == "主角信息"
    assert reply["tool_calls"][0]["result"][0]["name"] == "示例源"
    assert "secret" not in str(reply)
    assert len(service.get_conversation(conversation["id"], "7")["messages"]) == 2
    assert [event.action for event in audit.events] == ["ai.conversation.create", "ai.tool.invoke", "ai.conversation.message"]
    assert platform.calls[0]["provider_group"] == "ai"
    assert platform.calls[0]["model"] is None


@pytest.mark.asyncio
async def test_workspace_rejects_unknown_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "workspace.sqlite3"))

    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.core.exceptions import ValidationException
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    service = AIWorkspaceService(RecordingPlatform(), SQLiteAIConversationRepository(), SourceRepository(), TaskRepository(), AuditRepository())
    conversation = await service.create_conversation("7", "问答")

    with pytest.raises(ValidationException, match="Unsupported AI tool"):
        await service.send_message(conversation["id"], "7", "chat", "x", [{"name": "shell", "arguments": {}}])


@pytest.mark.asyncio
async def test_workspace_model_can_call_a_read_only_system_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "workspace-model-tools.sqlite3"))

    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    tool_call = {
        "id": "call-visible-sources",
        "type": "function",
        "function": {"name": "list_visible_sources", "arguments": "{}"},
    }

    class ToolCallingPlatform:
        def __init__(self):
            self.calls = []
            self.responses = [
                {
                    "output": {
                        "message": {"role": "assistant", "content": "", "tool_calls": [tool_call]},
                        "tool_calls": [tool_call],
                    },
                },
                {"output": {"text": "已读取可见书源。"}},
            ]

        async def invoke_chat(self, **kwargs):
            self.calls.append(kwargs)
            return self.responses.pop(0)

    bootstrap_sqlite()
    platform = ToolCallingPlatform()
    service = AIWorkspaceService(
        platform,
        SQLiteAIConversationRepository(),
        VisibleSourceRepository(),
        TaskRepository(),
        AuditRepository(),
    )
    conversation = await service.create_conversation("7")

    reply = await service.send_message(conversation["id"], "7", "chat", "列出我能看到的书源")

    assert reply["content"] == "已读取可见书源。"
    assert reply["tool_calls"][0]["name"] == "list_visible_sources"
    assert [item["id"] for item in reply["tool_calls"][0]["result"]] == ["owned-candidate", "published-source"]
    assert {item["function"]["name"] for item in platform.calls[0]["payload"]["tools"]} == {
        "list_visible_sources", "get_source_rule_summary", "list_ai_analysis_results",
    }
    assert platform.calls[1]["payload"]["messages"][-1]["role"] == "tool"
