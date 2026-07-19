import json

import pytest


class Source:
    def list_recent_versions(self, **_kwargs):
        return []


class Tasks:
    def list_tasks(self):
        return []


class Audit:
    def __init__(self):
        self.events = []

    async def record_audit(self, _event):
        self.events.append(_event)
        return _event


class Platform:
    def __init__(self):
        self.calls = []

    async def invoke_chat(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "search-1",
                        "type": "function",
                        "function": {"name": "source.search", "arguments": json.dumps({"keyword": "剑来"})},
                    }],
                },
            },
        }


class Executor:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, name, arguments):
        self.calls.append((name, arguments))
        return type("ToolResult", (), {
            "status": "accepted",
            "data": {"items": []},
            "error_code": None,
        })()


class PendingAuthorization:
    def __init__(self):
        self.created = []

    def active_tool_names(self, actor_id, conversation_id, rbac_permissions):
        return set()

    async def create_request(self, **kwargs):
        self.created.append(kwargs)
        return {
            "id": "request-1",
            "tools": ["source.search"],
            "purpose": "读取书源原文以便基于证据分析人物",
            "status": "pending",
            "choices": ["once", "conversation", "remember", "deny"],
            "expires_at": "2099-01-01T00:00:00",
        }


class ResumePlatform(Platform):
    def __init__(self):
        super().__init__()
        self.responses = [
            {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": "search-1",
                            "type": "function",
                            "function": {"name": "source.search", "arguments": json.dumps({"keyword": "剑来"})},
                        }],
                    },
                },
            },
            {"output": {"text": "已基于书源搜索结果继续回答。"}},
        ]

    async def invoke_chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_model_content_call_pauses_before_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "workspace-authorization.sqlite3"))

    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    platform = Platform()
    executor = Executor()
    authorization = PendingAuthorization()
    service = AIWorkspaceService(
        platform,
        SQLiteAIConversationRepository(),
        Source(),
        Tasks(),
        Audit(),
        novel_tool_executor=executor,
        authorization_service=authorization,
    )
    conversation = await service.create_conversation("7", "人物分析")

    reply = await service.send_message(
        conversation["id"],
        "7",
        "character",
        "分析主角",
        allowed_tool_names={"source.search", "toc.get", "chapter.fetch"},
    )

    assert reply["status"] == "authorization_required"
    assert reply["authorization_request"]["id"] == "request-1"
    assert executor.calls == []
    assert authorization.created[0]["requested_tools"] == ["source.search"]


@pytest.mark.asyncio
async def test_explicit_content_tool_request_also_pauses_before_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "workspace-explicit-authorization.sqlite3"))

    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    executor = Executor()
    authorization = PendingAuthorization()
    service = AIWorkspaceService(
        Platform(),
        SQLiteAIConversationRepository(),
        Source(),
        Tasks(),
        Audit(),
        novel_tool_executor=executor,
        authorization_service=authorization,
    )
    conversation = await service.create_conversation("7")

    reply = await service.send_message(
        conversation["id"],
        "7",
        "chat",
        "搜索剑来",
        tool_requests=[{"name": "source.search", "arguments": {"keyword": "剑来"}}],
        allowed_tool_names={"source.search"},
    )

    assert reply["status"] == "authorization_required"
    assert executor.calls == []


@pytest.mark.asyncio
async def test_once_decision_resumes_saved_call_exactly_once(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "workspace-authorization-resume.sqlite3"))

    from app.application.services.ai_authorization_service import AIConversationAuthorizationService
    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.infrastructure.persistence.sqlite.ai_authorization_repo_impl import SQLiteAIAuthorizationRepository
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    platform = ResumePlatform()
    executor = Executor()
    audit = Audit()
    authorization = AIConversationAuthorizationService(
        repo=SQLiteAIAuthorizationRepository(),
        audit=audit,
    )
    service = AIWorkspaceService(
        platform,
        SQLiteAIConversationRepository(),
        Source(),
        Tasks(),
        audit,
        novel_tool_executor=executor,
        authorization_service=authorization,
    )
    conversation = await service.create_conversation("7", "书源搜索")

    pending = await service.send_message(
        conversation["id"], "7", "chat", "搜索剑来",
        allowed_tool_names={"source.search", "toc.get", "chapter.fetch"},
    )
    request_id = pending["authorization_request"]["id"]

    resumed = await service.decide_authorization(
        request_id,
        actor_id="7",
        conversation_id=conversation["id"],
        decision="once",
        rbac_permissions={"book_sources.read"},
        allowed_tool_names={"source.search", "toc.get", "chapter.fetch"},
    )

    assert resumed["message"]["content"] == "已基于书源搜索结果继续回答。"
    assert executor.calls == [("source.search", {"keyword": "剑来", "tenant_id": "7"})]
    repeated = await service.decide_authorization(
        request_id,
        actor_id="7",
        conversation_id=conversation["id"],
        decision="once",
        rbac_permissions={"book_sources.read"},
        allowed_tool_names={"source.search", "toc.get", "chapter.fetch"},
    )
    assert repeated["message"]["id"] == resumed["message"]["id"]
    assert len(executor.calls) == 1


@pytest.mark.asyncio
async def test_deny_decision_never_invokes_source_executor(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "workspace-authorization-deny.sqlite3"))

    from app.application.services.ai_authorization_service import AIConversationAuthorizationService
    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.infrastructure.persistence.sqlite.ai_authorization_repo_impl import SQLiteAIAuthorizationRepository
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    executor = Executor()
    audit = Audit()
    authorization = AIConversationAuthorizationService(repo=SQLiteAIAuthorizationRepository(), audit=audit)
    service = AIWorkspaceService(
        Platform(),
        SQLiteAIConversationRepository(),
        Source(),
        Tasks(),
        audit,
        novel_tool_executor=executor,
        authorization_service=authorization,
    )
    conversation = await service.create_conversation("7")
    pending = await service.send_message(
        conversation["id"], "7", "chat", "搜索剑来",
        allowed_tool_names={"source.search"},
    )

    denied = await service.decide_authorization(
        pending["authorization_request"]["id"],
        actor_id="7",
        conversation_id=conversation["id"],
        decision="deny",
        rbac_permissions={"book_sources.read"},
        allowed_tool_names={"source.search"},
    )

    assert denied["message"]["status"] == "denied"
    assert denied["authorization"]["result_message_id"] == denied["message"]["id"]
    assert executor.calls == []


@pytest.mark.asyncio
async def test_reloading_conversation_hydrates_resolved_authorization_card(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "workspace-authorization-card.sqlite3"))

    from app.application.services.ai_authorization_service import AIConversationAuthorizationService
    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.infrastructure.persistence.sqlite.ai_authorization_repo_impl import SQLiteAIAuthorizationRepository
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    audit = Audit()
    authorization = AIConversationAuthorizationService(
        repo=SQLiteAIAuthorizationRepository(),
        audit=audit,
    )
    service = AIWorkspaceService(
        Platform(),
        SQLiteAIConversationRepository(),
        Source(),
        Tasks(),
        audit,
        novel_tool_executor=Executor(),
        authorization_service=authorization,
    )
    conversation = await service.create_conversation("7", "授权卡")
    pending = await service.send_message(
        conversation["id"],
        "7",
        "character",
        "分析主角",
        allowed_tool_names={"source.search", "toc.get", "chapter.fetch"},
    )
    request_id = pending["authorization_request"]["id"]

    await service.decide_authorization(
        request_id,
        actor_id="7",
        conversation_id=conversation["id"],
        decision="deny",
        rbac_permissions={"book_sources.read"},
        allowed_tool_names={"source.search", "toc.get", "chapter.fetch"},
    )

    reloaded = service.get_conversation(conversation["id"], "7")
    original_card = next(message for message in reloaded["messages"] if message["id"] == pending["id"])

    assert original_card["status"] != "authorization_required"
    assert original_card["authorization_request"]["status"] == "denied"


@pytest.mark.asyncio
async def test_malformed_model_tool_call_fails_without_creating_authorization_request(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "workspace-authorization-malformed.sqlite3"))

    from app.application.services.ai_authorization_service import AIConversationAuthorizationService
    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.infrastructure.persistence.sqlite.ai_authorization_repo_impl import SQLiteAIAuthorizationRepository
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    class MalformedPlatform(Platform):
        async def invoke_chat(self, **kwargs):
            self.calls.append(kwargs)
            return {"output": {"message": {"role": "assistant", "content": "", "tool_calls": [{
                "id": "bad-call",
                "type": "function",
                "function": {"name": "source.search", "arguments": "{not-json"},
            }]}}}

    bootstrap_sqlite()
    audit = Audit()
    authorization = AIConversationAuthorizationService(repo=SQLiteAIAuthorizationRepository(), audit=audit)
    service = AIWorkspaceService(
        MalformedPlatform(),
        SQLiteAIConversationRepository(),
        Source(),
        Tasks(),
        audit,
        novel_tool_executor=Executor(),
        authorization_service=authorization,
    )
    conversation = await service.create_conversation("7")

    reply = await service.send_message(
        conversation["id"], "7", "chat", "搜索剑来",
        allowed_tool_names={"source.search"},
    )

    assert reply["status"] == "failed"
    assert authorization.list_pending("7", conversation["id"]) == []
