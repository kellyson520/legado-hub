import pytest
from app.application.services.ai_workspace_service import AIWorkspaceService
from app.infrastructure.legado.engine.legado_native_semantics import LegadoJsCompatProfile
from app.infrastructure.legado.engine.js_worker_bridge import JsWorkerClient, JsExecutionContext


def test_requires_content_evidence_scope():
    assert AIWorkspaceService._requires_content_evidence("character", "任何内容") is True
    assert AIWorkspaceService._requires_content_evidence("storyline", "任何内容") is True
    assert AIWorkspaceService._requires_content_evidence("world", "任何内容") is True
    assert AIWorkspaceService._requires_content_evidence("chat", "介绍一下天才俱乐部") is False
    assert AIWorkspaceService._requires_content_evidence("chat", "你好，推荐几部好看的小说") is False


def test_authorized_content_tools_for_chat_mode():
    class DummyAuthService:
        def active_tool_names(self, actor_id, conversation_id, permissions):
            return set()

    service = AIWorkspaceService(
        platform=None,
        conversations=None,
        sources=None,
        ai_tasks=None,
        audit=None,
        authorization_service=DummyAuthService(),
    )
    tools = frozenset({"source.search", "toc.get", "chapter.fetch", "other_tool"})
    authorized = service._authorized_content_tools("user1", "conv1", tools, mode="chat")
    assert "source.search" in authorized
    assert "toc.get" in authorized
    assert "chapter.fetch" in authorized


def test_legado_compat_profile_search_stage_supported():
    profile = LegadoJsCompatProfile.native_defaults()
    assert "search" in profile.allowed_stages
    assert "toc" in profile.allowed_stages
    assert "content" in profile.allowed_stages
    assert "book_info" in profile.allowed_stages


def test_js_worker_client_missing_node_handled_gracefully():
    client = JsWorkerClient(node_binary="/nonexistent/path/to/node")
    context = JsExecutionContext(stage="search")
    output = client.execute("return 1 + 1", context)
    assert output.success is False
    assert output.error_code == "NODE_NOT_FOUND"
