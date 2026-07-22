from dataclasses import dataclass

import pytest


@dataclass
class Book:
    id: int = 7
    book_name: str = "测试书"
    author: str = "作者"
    summary_global: str = "林远在青云宗寻找答案。"


@dataclass
class Chapter:
    id: int
    book_id: int = 7
    canonical_num: int = 2
    chapter_title: str = "城门"
    raw_text: str = "林远在城门遇见周宁。"
    summary: str = "两人重逢。"


class ConversationRepository:
    def __init__(self):
        self.conversations = {}
        self.messages = {}

    def create_conversation(self, conversation):
        self.conversations[conversation.id] = conversation
        self.messages[conversation.id] = []
        return conversation

    def get_conversation(self, conversation_id, actor_id, owner_scope=None):
        conversation = self.conversations.get(conversation_id)
        if conversation is None or conversation.actor_id != str(actor_id):
            return None
        if owner_scope is not None and conversation.owner_scope != owner_scope:
            return None
        return conversation

    def append_message(self, message):
        self.messages[message.conversation_id].append(message)
        return message

    def list_messages(self, conversation_id, owner_scope=None):
        messages = self.messages.get(conversation_id, [])
        if owner_scope is None:
            return list(messages)
        return [item for item in messages if item.owner_scope == owner_scope]


class NovelRepository:
    async def get_book_by_id(self, owner_scope, book_id):
        return Book() if owner_scope == "user:1" and book_id == 7 else None

    async def get_chapter_by_id(self, owner_scope, chapter_id):
        return Chapter(id=chapter_id) if owner_scope == "user:1" and chapter_id == 2 else None

    async def get_reading_progress(self, owner_scope, book_id):
        if owner_scope == "user:1" and book_id == 7:
            return {"chapter_id": 2, "percent": 0.42, "offset_chars": 12}
        return None


class Platform:
    def __init__(self):
        self.calls = []

    async def invoke_chat(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "provider_name": "fake-provider",
            "model": kwargs.get("model") or "fake-model",
            "output": {"text": "基于当前上下文的回答"},
            "usage": {"input_tokens": 4, "output_tokens": 6},
            "cost": {"total": 0.01},
        }


class Retriever:
    async def retrieve(self, owner_scope, book_id, query, top_k=5, **_kwargs):
        return [
            type(
                "Evidence",
                (),
                {
                    "owner_scope": owner_scope,
                    "book_id": book_id,
                    "chapter_num": 2,
                    "source": "bm25",
                    "confidence": 0.9,
                    "evidence": "林远在城门遇见周宁。",
                    "content": "第2章 城门\n林远在城门遇见周宁。",
                },
            )()
        ][:top_k]


class Selection:
    def resolve_with_metadata(self, owner_scope, book_id, conversation_id, task_type, request_model):
        return type("Resolution", (), {"model": request_model or "fake-model", "source": "route", "provider_group": "novel_chat"})()


class Runtime:
    def __init__(self):
        self.history = []

    def create_run(self, **kwargs):
        run = type("Run", (), {"id": "run-1"})()
        self.history.append({"status": "started", **kwargs})
        return run

    def record_tool_invocation(self, **kwargs):
        item = {"status": "invoked", **kwargs}
        self.history.append(item)
        return type("Invocation", (), {"id": "invocation-1"})()

    def record_tool_result(self, **kwargs):
        item = {"status": kwargs["status"], **kwargs}
        self.history.append(item)
        return item


@pytest.fixture
def service():
    from app.application.services.novel_agent_app_service import NovelAgentAppService

    platform = Platform()
    runtime = Runtime()
    return NovelAgentAppService(
        platform=platform,
        conversations=ConversationRepository(),
        novel_repo=NovelRepository(),
        retriever=Retriever(),
        model_selection=Selection(),
        agent_runtime=runtime,
    )


@pytest.mark.asyncio
async def test_same_conversation_continues_from_workspace_book_page_and_reader(service):
    conversation = await service.create_conversation("user:1", title="阅读助手", book_id=7, entrypoint="workspace")
    await service.send_message("user:1", conversation["id"], "人物出现次数", entrypoint="workspace")
    await service.send_message(
        "user:1", conversation["id"], "继续分析当前章节", entrypoint="book", chapter_id=2
    )
    await service.send_message(
        "user:1", conversation["id"], "这段关系有什么证据", entrypoint="reader", chapter_id=2
    )

    assert len(service.get_conversation("user:1", conversation["id"])["messages"]) == 6
    assert service._platform.calls[-1]["provider_group"] == "novel_chat"
    assert service.get_conversation("user:1", conversation["id"])["messages"][-1]["entrypoint"] == "reader"


@pytest.mark.asyncio
async def test_reader_conversation_reuses_its_initial_chapter_when_message_omits_it(service):
    conversation = await service.create_conversation(
        "user:1", book_id=7, chapter_id=2, entrypoint="reader"
    )

    assert conversation["chapter_id"] == 2
    await service.send_message("user:1", conversation["id"], "继续", entrypoint="reader", book_id=7)

    messages = service.get_conversation("user:1", conversation["id"])["messages"]
    assert messages[0]["chapter_id"] == 2


@pytest.mark.asyncio
async def test_cross_owner_operate_tool_is_rejected_and_audited(service):
    from app.core.exceptions import AuthorizationException

    with pytest.raises(AuthorizationException):
        await service.call_tool("user:1", "knowledge.propose", {"owner_scope": "user:2"})

    assert service._agent_runtime.history[-1]["status"] == "rejected"


@pytest.mark.asyncio
async def test_reader_context_contains_scoped_evidence_and_untrusted_boundary(service):
    conversation = await service.create_conversation("user:1", book_id=7, entrypoint="reader")
    answer = await service.send_message(
        "user:1",
        conversation["id"],
        "读取这一章",
        entrypoint="reader",
        book_id=7,
        chapter_id=2,
    )

    assert answer["content"] == "基于当前上下文的回答"
    payload = service._platform.calls[-1]["payload"]
    assert "untrusted evidence" in payload["messages"][0]["content"].lower()
    assert "林远在城门遇见周宁" in str(payload)


@pytest.mark.asyncio
async def test_model_payload_serializes_novel_tools_as_openai_functions(service):
    conversation = await service.create_conversation("user:1", book_id=7, entrypoint="book")

    await service.send_message(
        "user:1",
        conversation["id"],
        "这本书讲述的什么故事",
        entrypoint="book",
        book_id=7,
    )

    tools = service._platform.calls[-1]["payload"]["tools"]
    assert tools
    assert all(item["type"] == "function" for item in tools)
    assert all("name" in item["function"] for item in tools)
    assert all("description" in item["function"] for item in tools)
    assert all("parameters" in item["function"] for item in tools)


@pytest.mark.asyncio
async def test_read_tool_is_scoped_and_runtime_records_accepted_result(service):
    result = await service.call_tool(
        "user:1",
        "reading.progress",
        {"book_id": 7},
        book_id=7,
    )

    assert result["category"] == "read"
    assert result["result"]["percent"] == 0.42
    assert service._agent_runtime.history[-1]["status"] == "accepted"


@pytest.mark.asyncio
async def test_final_answer_cache_is_scoped_and_records_usage(service):
    class Cache:
        def __init__(self):
            self.values = {}

        def key(self, **kwargs):
            return "|".join(str(kwargs[item]) for item in ("owner_scope", "book_id", "model", "task_type", "query"))

        async def get(self, key):
            return self.values.get(key)

        async def set(self, key, value, expire=None):
            self.values[key] = value
            return True

    service._cache = Cache()
    conversation = await service.create_conversation("user:1")
    first = await service.send_message("user:1", conversation["id"], "相同问题", entrypoint="workspace")
    calls_after_first = len(service._platform.calls)
    second = await service.send_message("user:1", conversation["id"], "相同问题", entrypoint="workspace")

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert len(service._platform.calls) == calls_after_first


@pytest.mark.asyncio
async def test_legacy_novel_agent_service_forwards_to_unified_application_service():
    from app.application.services.novel_agent_service import NovelAgentService

    class App:
        async def create_conversation(self, *args, **kwargs):
            return {"id": "conversation-1", "args": args, "kwargs": kwargs}

    service = NovelAgentService(app_service=App())
    result = await service.create_conversation("user:1", book_id=7, entrypoint="book")

    assert result["id"] == "conversation-1"
    assert result["args"] == ("user:1", "")
    assert result["kwargs"]["book_id"] == 7


def test_factory_exposes_unified_novel_agent_builder(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "factory-novel-agent.sqlite3"))

    from app.application.services.novel_agent_app_service import NovelAgentAppService
    from app.infrastructure.persistence.factory import build_novel_agent_app_service

    service = build_novel_agent_app_service()

    assert isinstance(service, NovelAgentAppService)
