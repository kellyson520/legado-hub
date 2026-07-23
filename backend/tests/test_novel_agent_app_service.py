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

    async def get_entity_by_name(self, owner_scope, book_id, name):
        if owner_scope != "user:1" or book_id != 7 or name not in {"林远", "玄天剑"}:
            return None
        return type(
            "Entity",
            (),
            {
                "id": 11 if name == "林远" else 12,
                "book_id": book_id,
                "name": name,
                "aliases": ["林兄"] if name == "林远" else [],
                "entity_type": "character" if name == "林远" else "item",
                "description": "主角" if name == "林远" else "佩剑",
                "first_appearance_ch": 1,
                "last_appearance_ch": 2,
                "appearance_count": 3,
                "attributes": {
                    "confidence": 0.92,
                    "evidence": [{"chapter_id": 2, "chapter_num": 2, "text": f"第2章提到{name}"}],
                },
            },
        )()

    async def search_entities(self, owner_scope, book_id, keyword, entity_type=None, limit=20):
        entity = await self.get_entity_by_name(owner_scope, book_id, "林远")
        return [entity] if entity and keyword in entity.name else []

    async def list_entities(self, owner_scope, book_id, entity_type=None, limit=50, offset=0):
        entities = [
            await self.get_entity_by_name(owner_scope, book_id, "林远"),
            await self.get_entity_by_name(owner_scope, book_id, "玄天剑"),
        ]
        return [entity for entity in entities if entity is not None][:limit]

    async def count_entities(self, owner_scope, book_id, entity_type=None):
        return 2

    async def count_chapters(self, owner_scope, book_id):
        return 2

    async def get_relationships_by_entity(self, owner_scope, book_id, entity_name, limit=50):
        if owner_scope != "user:1" or entity_name != "林远":
            return []
        return [
            type(
                "Relation",
                (),
                {
                    "source_entity": "林远",
                    "target_entity": "周宁",
                    "relation_type": "ally",
                    "description": "并肩作战",
                    "since_chapter": 2,
                    "confidence": 0.9,
                    "evidence": [{"chapter_id": 2, "chapter_num": 2, "text": "林远与周宁并肩作战"}],
                },
            )()
        ]

    async def get_events(self, owner_scope, book_id, chapter_num=None, event_type=None, min_importance=1, limit=50):
        return [
            type(
                "Event",
                (),
                {
                    "id": 21,
                    "book_id": book_id,
                    "chapter_id": 2,
                    "chapter_num": 2,
                    "event_type": "battle",
                    "description": "城门冲突",
                    "participants": ["林远", "周宁"],
                    "importance": 4,
                    "evidence": [{"chapter_id": 2, "chapter_num": 2, "text": "城门冲突"}],
                },
            )()
        ][:limit]

    async def get_state_changes(self, owner_scope, book_id, entity_name=None, field_name=None, limit=50):
        if entity_name != "玄天剑":
            return []
        return [
            type(
                "State",
                (),
                {
                    "entity_name": "玄天剑",
                    "chapter_id": 2,
                    "chapter_num": 2,
                    "field_name": "possession",
                    "before_value": "",
                    "after_value": "林远",
                    "confidence": 0.88,
                    "evidence": [{"chapter_id": 2, "chapter_num": 2, "text": "林远获得玄天剑"}],
                },
            )()
        ][:limit]

    async def get_chapters_by_book(self, owner_scope, book_id, start_num=0, end_num=None, limit=100, offset=0):
        return [Chapter(id=2)]

    async def list_index_states(self, owner_scope, book_id):
        return [
            type(
                "IndexState",
                (),
                {
                    "chapter_id": 2,
                    "content_hash": "hash",
                    "knowledge_version": "v1",
                    "extraction_status": "completed",
                    "bm25_status": "completed",
                    "vector_status": "disabled",
                    "failure_reason": "",
                    "updated_at": "2026-07-22T00:00:00+00:00",
                },
            )()
        ]


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
async def test_novel_agent_uses_bounded_recent_message_query(service):
    conversation = await service.create_conversation("user:1", title="最近消息")
    recent_calls = []

    def list_recent_messages(conversation_id, owner_scope=None, limit=12):
        recent_calls.append((conversation_id, owner_scope, limit))
        return service._conversations.messages[conversation_id][-limit:]

    service._conversations.list_recent_messages = list_recent_messages
    await service.send_message("user:1", conversation["id"], "测试最近消息", entrypoint="workspace")

    assert recent_calls == [(conversation["id"], "user:1", 12)]


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
async def test_character_tools_return_book_scoped_collections_when_name_is_omitted(service):
    counts = await service.call_tool(
        "user:1",
        "character.count",
        {"book_id": 7},
        book_id=7,
    )
    aliases = await service.call_tool(
        "user:1",
        "character.aliases",
        {"book_id": 7},
        book_id=7,
    )
    relations = await service.call_tool(
        "user:1",
        "character.relations",
        {"book_id": 7},
        book_id=7,
    )

    assert counts["result"][0]["name"] == "林远"
    assert counts["result"][0]["appearance_count"] == 3
    assert aliases["result"][0]["aliases"] == ["林兄"]
    assert relations["result"][0]["source_entity"] == "林远"


@pytest.mark.asyncio
async def test_novel_tools_rebuild_empty_projection_from_chapter_text():
    import aiosqlite

    from app.application.services.novel_agent_app_service import NovelAgentAppService
    from app.application.services.novel_understanding.retriever import RAGRetriever
    from app.domain.entities.novel import NovelBook, NovelChapter
    from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository

    db = await aiosqlite.connect(":memory:")
    try:
        with open("app/database_migrations/novel_schema.sql", encoding="utf-8") as schema:
            await db.executescript(schema.read())
        repo = SqliteNovelRepository(db)
        book = await repo.save_book(
            "user:1",
            NovelBook(book_url="upload:test", book_name="测试书", total_chapters=1),
        )
        await repo.save_chapter(
            "user:1",
            NovelChapter(
                book_id=book.id,
                canonical_num=1,
                chapter_title="相遇",
                raw_text="林远走进青云宗，周宁在门前等他。林远与周宁并肩作战。",
            ),
        )
        service = NovelAgentAppService(novel_repo=repo, retriever=RAGRetriever(repo))

        profile = await service.call_tool(
            "user:1",
            "novel.get_entity_profile",
            {"book_id": book.id, "name": "林远"},
            book_id=book.id,
        )
        counts = await service.call_tool(
            "user:1",
            "character.count",
            {"book_id": book.id},
            book_id=book.id,
        )
        aliases = await service.call_tool(
            "user:1",
            "character.aliases",
            {"book_id": book.id},
            book_id=book.id,
        )
        relations = await service.call_tool(
            "user:1",
            "character.relations",
            {"book_id": book.id},
            book_id=book.id,
        )
        chapter_search = await service.call_tool(
            "user:1",
            "chapter.search",
            {"book_id": book.id, "query": "林远"},
            book_id=book.id,
        )
        semantic_search = await service.call_tool(
            "user:1",
            "semantic.search",
            {"book_id": book.id, "query": "林远"},
            book_id=book.id,
        )

        assert profile["result"]["name"] == "林远"
        assert counts["result"]
        assert aliases["result"]
        assert relations["result"]
        assert chapter_search["result"]
        assert semantic_search["result"]
        refreshed = await repo.get_book_by_id("user:1", book.id)
        assert refreshed.character_count >= 2
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_local_fallback_does_not_replace_existing_projection():
    from app.application.services.novel_agent_app_service import NovelAgentAppService
    from app.domain.entities.novel import EntityType

    class ExistingProjectionRepository(NovelRepository):
        def __init__(self):
            self.replace_calls = 0
            self.existing = type(
                "Entity",
                (),
                {
                    "book_id": 7,
                    "name": "玄天剑",
                    "aliases": [],
                    "entity_type": EntityType.ITEM,
                    "description": "已有物品知识",
                    "first_appearance_ch": 1,
                    "last_appearance_ch": 1,
                    "appearance_count": 1,
                    "importance_score": 3,
                    "attributes": {},
                },
            )()

        async def list_entities(self, _owner_scope, _book_id, limit=50, offset=0, **_kwargs):
            return [self.existing][offset : offset + limit]

        async def list_index_states(self, _owner_scope, _book_id):
            return []

        async def get_chapters_by_book(self, _owner_scope, _book_id, **_kwargs):
            return [Chapter(id=2, raw_text="林远走进青云宗，周宁在门前等他。林远与周宁并肩作战。")]

        async def replace_book_knowledge(self, *_args, **_kwargs):
            self.replace_calls += 1

    repo = ExistingProjectionRepository()
    service = NovelAgentAppService(novel_repo=repo)

    result = await service.call_tool(
        "user:1",
        "character.count",
        {"book_id": 7},
        book_id=7,
    )

    assert result["result"]
    assert any(item["name"] == "林远" for item in result["result"])
    assert repo.replace_calls == 0


@pytest.mark.asyncio
async def test_named_profile_falls_back_when_projection_contains_only_other_entities():
    from app.application.services.novel_agent_app_service import NovelAgentAppService
    from app.domain.entities.novel import EntityType

    class MixedProjectionRepository(NovelRepository):
        async def get_entity_by_name(self, *_args, **_kwargs):
            return None

        async def search_entities(self, *_args, **_kwargs):
            return []

        async def list_entities(self, _owner_scope, _book_id, limit=50, offset=0, **_kwargs):
            return [
                type(
                    "Entity",
                    (),
                    {
                        "book_id": 7,
                        "name": "玄天剑",
                        "aliases": [],
                        "entity_type": EntityType.ITEM,
                        "description": "物品",
                        "first_appearance_ch": 1,
                        "last_appearance_ch": 1,
                        "appearance_count": 1,
                        "importance_score": 3,
                        "attributes": {},
                    },
                )()
            ][offset : offset + limit]

        async def list_index_states(self, _owner_scope, _book_id):
            return []

        async def get_events(self, *_args, **_kwargs):
            return []

        async def get_state_changes(self, *_args, **_kwargs):
            return []

        async def get_chapters_by_book(self, _owner_scope, _book_id, **_kwargs):
            return [Chapter(id=2, raw_text="林远走进青云宗，周宁在门前等他。林远与周宁并肩作战。")]

        async def replace_book_knowledge(self, *_args, **_kwargs):
            raise AssertionError("existing projection must not be replaced")

    service = NovelAgentAppService(novel_repo=MixedProjectionRepository())

    result = await service.call_tool(
        "user:1",
        "novel.get_entity_profile",
        {"book_id": 7, "name": "林远"},
        book_id=7,
    )

    assert result["result"]["name"] == "林远"
    assert result["result"].get("appearance_count", 0) > 0


@pytest.mark.asyncio
async def test_local_fallback_ignores_failed_or_stale_snapshot():
    from hashlib import sha256

    from app.application.services.novel_agent_app_service import NovelAgentAppService

    class StaleSnapshotRepository(NovelRepository):
        def __init__(self):
            self.replace_calls = []

        async def list_entities(self, *_args, **_kwargs):
            return []

        async def list_index_states(self, _owner_scope, _book_id):
            return [
                type(
                    "IndexState",
                    (),
                    {
                        "chapter_id": 2,
                        "content_hash": "old-hash",
                        "knowledge_version": "v2-local-evidence",
                        "extraction_status": "failed",
                        "extraction_payload": {
                            "chapter_id": 2,
                            "chapter_num": 2,
                            "content_hash": "old-hash",
                            "entities": [{"name": "旧人物", "entity_type": "character"}],
                        },
                    },
                )()
            ]

        async def get_chapters_by_book(self, _owner_scope, _book_id, **_kwargs):
            return [Chapter(id=2, raw_text="林远走进青云宗，周宁在门前等他。林远与周宁并肩作战。")]

        async def get_events(self, *_args, **_kwargs):
            return []

        async def get_state_changes(self, *_args, **_kwargs):
            return []

        async def replace_book_knowledge(self, _owner_scope, _book_id, snapshots):
            self.replace_calls.append(snapshots)

    repo = StaleSnapshotRepository()
    service = NovelAgentAppService(novel_repo=repo)

    result = await service.call_tool(
        "user:1",
        "character.count",
        {"book_id": 7},
        book_id=7,
    )

    current_hash = sha256("林远走进青云宗，周宁在门前等他。林远与周宁并肩作战。".encode("utf-8")).hexdigest()
    assert repo.replace_calls
    assert repo.replace_calls[0][0]["content_hash"] == current_hash
    assert result["result"]
    assert all(item["name"] != "旧人物" for item in result["result"])


@pytest.mark.asyncio
async def test_local_fallback_persists_completed_states_for_reuse(monkeypatch):
    from app.application.services.novel_agent_app_service import NovelAgentAppService
    from app.application.services.novel_understanding.auto_extractor import AutoExtractor

    class PersistedStateRepository(NovelRepository):
        def __init__(self):
            self.states = []

        async def list_entities(self, *_args, **_kwargs):
            return []

        async def list_index_states(self, _owner_scope, _book_id):
            return list(self.states)

        async def get_events(self, *_args, **_kwargs):
            return []

        async def get_state_changes(self, *_args, **_kwargs):
            return []

        async def save_index_state(self, state):
            self.states.append(state)

        async def replace_book_knowledge(self, *_args, **_kwargs):
            return None

    calls = []
    original = AutoExtractor.extract_with_evidence

    def tracked_extract(self, *args, **kwargs):
        calls.append((args, kwargs))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(AutoExtractor, "extract_with_evidence", tracked_extract)
    repo = PersistedStateRepository()

    first = NovelAgentAppService(novel_repo=repo)
    await first.call_tool("user:1", "character.count", {"book_id": 7}, book_id=7)
    second = NovelAgentAppService(novel_repo=repo)
    await second.call_tool("user:1", "character.count", {"book_id": 7}, book_id=7)

    assert len(repo.states) == 1
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_novel_read_tools_expose_evidence_and_knowledge_version(service):
    expected = {
        "novel.search_memory",
        "novel.get_entity_profile",
        "novel.get_mentions",
        "novel.get_relations",
        "novel.timeline",
        "novel.get_item_state",
        "novel.compare_entities",
        "novel.get_chapter_evidence",
        "novel.index_status",
    }
    tools = await service.list_tools("user:1", 7)
    assert expected <= {item["name"] for item in tools}

    profile = await service.call_tool("user:1", "novel.get_entity_profile", {"book_id": 7, "name": "林远"}, book_id=7)
    mentions = await service.call_tool("user:1", "novel.get_mentions", {"book_id": 7, "name": "林远"}, book_id=7)
    relations = await service.call_tool("user:1", "novel.get_relations", {"book_id": 7, "name": "林远"}, book_id=7)
    timeline = await service.call_tool("user:1", "novel.timeline", {"book_id": 7}, book_id=7)
    item_state = await service.call_tool("user:1", "novel.get_item_state", {"book_id": 7, "name": "玄天剑"}, book_id=7)
    comparison = await service.call_tool("user:1", "novel.compare_entities", {"book_id": 7, "left": "林远", "right": "玄天剑"}, book_id=7)
    evidence = await service.call_tool("user:1", "novel.get_chapter_evidence", {"book_id": 7, "chapter_id": 2}, book_id=7, chapter_id=2)
    status = await service.call_tool("user:1", "novel.index_status", {"book_id": 7}, book_id=7)

    assert profile["result"]["knowledge_version"] == service.knowledge_version
    assert profile["result"]["evidence"]
    assert mentions["result"][0]["chapter_id"] == 2
    assert relations["result"][0]["evidence"]
    assert timeline["result"][0]["chapter_num"] == 2
    assert item_state["result"][0]["evidence"]
    assert comparison["result"]["left"]["name"] == "林远"
    assert evidence["result"]["chapter_id"] == 2
    assert status["result"]["states"][0]["knowledge_version"] == "v1"


@pytest.mark.asyncio
async def test_novel_search_memory_passes_shared_version_and_requested_limit(service):
    class VersionedRetriever:
        def __init__(self):
            self.calls = []

        async def retrieve(self, owner_scope, book_id, query, *, top_k, knowledge_version):
            self.calls.append((owner_scope, book_id, query, top_k, knowledge_version))
            return []

    retriever = VersionedRetriever()
    service._retriever = retriever

    result = await service.call_tool(
        "user:1",
        "novel.search_memory",
        {"book_id": 7, "query": "玄天剑", "top_k": 9},
        book_id=7,
    )

    assert result["result"] == []
    assert retriever.calls == [("user:1", 7, "玄天剑", 9, service.knowledge_version)]


@pytest.mark.asyncio
async def test_novel_timeline_is_chronological_and_relation_limit_is_forwarded(service):
    async def events(_owner_scope, _book_id, chapter_num=None, event_type=None, min_importance=1, limit=50):
        del chapter_num, event_type, min_importance
        values = [
            type("Event", (), {"id": 3, "chapter_id": 3, "chapter_num": 3, "event_type": "battle", "description": "后续", "participants": [], "evidence": []})(),
            type("Event", (), {"id": 1, "chapter_id": 1, "chapter_num": 1, "event_type": "battle", "description": "开端", "participants": [], "evidence": []})(),
        ]
        return values[:limit]

    relation_calls = []

    async def relations(_owner_scope, _book_id, entity_name, limit=50):
        relation_calls.append(limit)
        return []

    service._novel_repo.get_events = events
    service._novel_repo.get_relationships_by_entity = relations

    timeline = await service.call_tool("user:1", "novel.timeline", {"book_id": 7}, book_id=7)
    await service.call_tool(
        "user:1",
        "novel.get_relations",
        {"book_id": 7, "name": "林远", "limit": 1},
        book_id=7,
    )

    assert timeline["result"][0]["chapter_num"] == 1
    assert relation_calls == [1]


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
