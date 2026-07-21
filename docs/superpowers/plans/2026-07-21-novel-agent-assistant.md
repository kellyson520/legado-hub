# Novel Agent Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有小说模型、书源读取、小说理解、Provider 路由、缓存、会话和前端 AI 工作台整合为一个按用户隔离、可持久续读、支持上传/书源/网络导入的小说 Agent 助手，并接入独立助手、书籍详情页和阅读器内助手。

**Architecture:** 继续以 NovelBook、NovelChapter、现有知识实体和 NovelRepository 为唯一小说内容模型；NovelIngestionService 统一三类输入，NovelIndexService 负责增量理解与混合检索，NovelAgentAppService 只编排上下文、会话、工具和 Provider，不复制抓取、Provider 或缓存实现。所有内容、会话、索引、工具调用和缓存显式带 owner_scope，系统管理员配置 Provider、模型、Embedding、VectorStore 和工具权限，普通用户只能选择开放模型。

**Tech Stack:** Python 3、FastAPI、Pydantic 2、SQLAlchemy/SQLite、aiosqlite、httpx、BeautifulSoup/lxml、现有 CacheProvider、Redis/内存降级、现有 NovelAgent/ToolRegistry/AgentRuntimeService、React 18、TypeScript、Vite、Vitest、Testing Library。

---

## 文件地图

实现前按下表确认边界。修改现有文件时保持既有 API 和测试兼容；不创建第二套 Book/Chapter、Agent 注册表、Provider 客户端或缓存接口。

### 领域、仓储和数据库

- Modify: backend/app/domain/value_objects.py — 增加不可变 OwnerScope 和模型选择值对象。
- Modify: backend/app/domain/entities/novel.py — 给 NovelBook 增加归属字段，并保持章节通过书籍继承归属。
- Modify: backend/app/domain/entities/novel_runtime.py — 扩展摄入/分析任务，增加 NovelIndexState 和模型偏好实体。
- Modify: backend/app/domain/entities/ai_conversation.py — 增加书籍、入口、上下文范围、模型覆盖和归属信息。
- Modify: backend/app/domain/repositories/novel_repo.py — 所有读写方法显式接收 owner_scope，增加索引状态和证据查询。
- Modify: backend/app/domain/repositories/novel_runtime_repo.py — 摄入、任务和索引状态按归属查询。
- Modify: backend/app/domain/repositories/ai_conversation_repo.py — 会话和消息仓储按归属及主体查询。
- Create: backend/app/domain/repositories/novel_model_preference_repo.py — 用户、书籍、会话模型覆盖的唯一仓储端口。
- Modify: backend/app/infrastructure/persistence/sqlite/schema.py — 主 SQLite 数据库的会话、任务、Provider 配置和本地向量表。
- Modify: backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py — 正式小说内容仓储的归属过滤、索引状态和进度读写。
- Modify: backend/app/infrastructure/persistence/sqlite/novel_runtime_repo_impl.py — 摄入/任务/索引状态的归属过滤。
- Modify: backend/app/infrastructure/persistence/sqlite/ai_conversation_repo_impl.py — 会话/消息的归属过滤和上下文字段转换。
- Create: backend/app/infrastructure/persistence/sqlite/novel_model_preference_repo_impl.py — 模型偏好 SQLite 实现。
- Modify: backend/app/infrastructure/persistence/sqlite/bootstrap.py — 现有数据库的幂等列、索引和默认路由迁移。
- Modify: backend/app/database_migrations/novel_schema.sql — 新建数据库使用的正式小说、进度、索引状态和本地向量表。
- Create: backend/app/infrastructure/persistence/sqlite/novel_db_migrator.py — 对已有 data/novel.db 执行可恢复的 SQLite 迁移。

### 导入、理解、检索和 Agent

- Create: backend/app/services/novel_ingestion/__init__.py、parsers.py、url_security.py — 文档解析和网络安全设施。
- Modify: backend/app/application/services/novel_ingestion_service.py — 上传、书源、网络链接统一摄入和内容哈希幂等。
- Create: backend/app/domain/repositories/vector_store.py — VectorStore 端口和向量记录类型。
- Create: backend/app/infrastructure/vectorstores/__init__.py、disabled.py、sqlite.py、qdrant.py、pgvector.py — 关闭、本地、Qdrant、pgvector 适配器。
- Modify: backend/app/services/novel_understanding/embedding.py — 通过 Provider 路由获取 Embedding。
- Modify: backend/app/services/novel_understanding/bm25_index.py、retriever.py — 书籍/版本隔离和真实混合检索。
- Create: backend/app/services/novel_understanding/index_service.py、structured_extractor.py — 增量理解和结构化输出校验。
- Create: backend/app/application/services/novel_model_selection_service.py、novel_cache_service.py、novel_agent_app_service.py — 模型覆盖、缓存和统一 Agent 编排。
- Modify: backend/app/application/services/novel_agent_service.py、ai_workspace_service.py、agent_runtime_service.py、agent_tool_registry.py — 兼容转发、共享上下文、审计和工具。
- Modify: backend/app/application/services/provider_platform_service.py、backend/app/infrastructure/providers/base.py、openai_compatible.py、registry.py — 四个小说任务路由和 Embedding 能力。
- Modify: backend/app/infrastructure/persistence/factory.py、backend/app/tasks/scheduler.py；Create: backend/app/tasks/novel_index_worker.py — 统一依赖组装和后台索引任务。

### API、系统配置和前端

- Modify: backend/app/interfaces/http/deps.py、ai.py、novel.py、system.py、backend/app/interfaces/api/v1/novel_agent.py、backend/app/main.py — 认证 API、兼容 chat、导入、流式响应和系统配置。
- Modify: backend/app/application/services/system_settings_service.py — 小说 Agent 配置读取、校验、脱敏和健康状态。
- Create: backend/tests/test_novel_owner_scope.py、test_novel_import_service.py、test_novel_url_security.py、test_novel_model_selection.py、test_novel_cache_service.py、test_vector_store.py、test_novel_index_service.py、test_novel_agent_app_service.py、test_api_novel_agent.py、test_novel_security.py。
- Modify: backend/tests/test_novel_repo.py、test_novel_ingestion_service.py、test_rag_retriever.py、test_provider_platform_service.py、test_ai_workspace_service.py、test_api_ai_workspace.py。
- Modify: frontend/src/api/modules/ai.ts、novel.ts；Create: frontend/src/features/novel/NovelLibraryPage.tsx、NovelLibraryPage.test.tsx、NovelReaderPage.tsx、NovelReaderPage.test.tsx。
- Modify: frontend/src/features/ai/AIWorkspacePage.tsx、AIWorkspacePage.test.tsx、frontend/src/features/system/ProviderRoutingSettings.tsx、ProviderRoutingSettings.test.tsx、frontend/src/app/router.tsx、navigation.tsx。

## 实施任务

### Task 1: 建立 owner_scope、正式数据模型和可迁移数据库

**Files:**
- Modify: backend/app/domain/value_objects.py
- Modify: backend/app/domain/entities/novel.py、novel_runtime.py、ai_conversation.py
- Modify: backend/app/domain/repositories/novel_repo.py、novel_runtime_repo.py、ai_conversation_repo.py
- Create: backend/app/domain/repositories/novel_model_preference_repo.py
- Modify: backend/app/infrastructure/persistence/sqlite/schema.py、novel_repo_impl.py、novel_runtime_repo_impl.py、ai_conversation_repo_impl.py、bootstrap.py
- Create: backend/app/infrastructure/persistence/sqlite/novel_model_preference_repo_impl.py、novel_db_migrator.py
- Modify: backend/app/database_migrations/novel_schema.sql
- Test: backend/tests/test_novel_owner_scope.py and existing novel repository tests

- [ ] Step 1: Write the failing isolation test.

~~~python
@pytest.mark.asyncio
async def test_book_chapter_and_knowledge_queries_are_scoped(repo):
    first = await repo.save_book("user:1", NovelBook(book_url="https://book.test/1", book_name="甲本"))
    second = await repo.save_book("user:2", NovelBook(book_url="https://book.test/1", book_name="乙本"))
    await repo.save_chapter("user:1", NovelChapter(book_id=first.id, canonical_full="C1", canonical_num=1, raw_text="甲本正文"))
    await repo.save_entity("user:1", NovelEntity(book_id=first.id, name="甲人物"))

    assert await repo.get_book_by_id("user:2", first.id) is None
    assert len(await repo.list_books("user:1")) == 1
    assert len(await repo.list_books("user:2")) == 1
    assert await repo.get_chapters_by_book("user:2", first.id) == []
    assert await repo.search_entities("user:2", first.id, "甲人物") == []
    assert second.owner_scope == "user:2"
~~~

Run: cd backend && pytest -q tests/test_novel_owner_scope.py tests/test_novel_repo.py

Expected: FAIL because methods lack explicit scope and book_url is globally unique.

- [ ] Step 2: Define the scope and repository contracts.

Use this value object:

~~~python
@dataclass(frozen=True)
class OwnerScope:
    value: str
    kind: Literal["user", "api_key"]

    @classmethod
    def user(cls, user_id: int) -> "OwnerScope":
        return cls(f"user:{int(user_id)}", "user")

    @classmethod
    def api_key(cls, api_key_id: int) -> "OwnerScope":
        return cls(f"api-key:{int(api_key_id)}", "api_key")

    def __str__(self) -> str:
        return self.value
~~~

Every NovelRepository content method uses owner_scope as its first argument, including save/get/list book, chapter, entity, relationship, event, state, index-state and progress methods. Chapter and knowledge queries join through novels.owner_scope; a caller cannot use only a chapter ID. Runtime and conversation repositories receive the same explicit argument. Add owner_scope, book_id, entrypoint, context_range, model_ref, knowledge_version and toolset_version to the relevant dataclasses. Keep actor_id for audit, but use owner_scope for authorization and cache identity.

- [ ] Step 3: Add the schema and migration.

Update fresh schema with:

~~~sql
ALTER TABLE novels ADD COLUMN owner_scope TEXT NOT NULL DEFAULT 'legacy';
CREATE UNIQUE INDEX IF NOT EXISTS ux_novels_owner_url ON novels(owner_scope, book_url);
CREATE INDEX IF NOT EXISTS idx_novels_owner_updated ON novels(owner_scope, updated_at DESC);

CREATE TABLE IF NOT EXISTS novel_index_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_scope TEXT NOT NULL,
    book_id INTEGER NOT NULL,
    chapter_id INTEGER,
    content_hash TEXT NOT NULL DEFAULT '',
    knowledge_version TEXT NOT NULL DEFAULT '',
    extraction_status TEXT NOT NULL DEFAULT 'pending',
    bm25_status TEXT NOT NULL DEFAULT 'pending',
    vector_status TEXT NOT NULL DEFAULT 'disabled',
    embedding_model TEXT NOT NULL DEFAULT '',
    embedding_dimension INTEGER NOT NULL DEFAULT 0,
    last_success_at TIMESTAMP,
    failure_reason TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(book_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE(owner_scope, book_id, chapter_id)
);

CREATE TABLE IF NOT EXISTS novel_reading_progress (
    owner_scope TEXT NOT NULL,
    book_id INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    offset_chars INTEGER NOT NULL DEFAULT 0,
    percent REAL NOT NULL DEFAULT 0.0,
    theme TEXT NOT NULL DEFAULT 'paper',
    background TEXT NOT NULL DEFAULT '',
    font_size INTEGER NOT NULL DEFAULT 18,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(owner_scope, book_id),
    FOREIGN KEY(book_id) REFERENCES novels(id) ON DELETE CASCADE
);
~~~

novel_db_migrator.py inspects PRAGMA table_info, rebuilds the old globally-unique novels table if needed, backfills legacy rows as owner_scope=legacy, and changes PRAGMA user_version only after commit. bootstrap.py adds idempotent columns/indexes to ai_conversations, ai_tasks, novel_ingestions, novel_tasks and provider routes, and adds the four new route groups without removing old routes.

- [ ] Step 4: Implement owner-filtered persistence and update fixtures.

Use scope in every SQL predicate:

~~~python
async def get_book_by_id(self, owner_scope: str, book_id: int) -> NovelBook | None:
    async with self._db.execute(
        "SELECT * FROM novels WHERE owner_scope=? AND id=?",
        (owner_scope, book_id),
    ) as cursor:
        row = await cursor.fetchone()
    return self._row_to_book(row) if row else None
~~~

Update repository, ingestion and RAG fixtures to pass user:test. Row converters use column names or migration-safe projections, not the old positional-length branch. Save chapter/entity/relationship/event/state first verifies the referenced book belongs to the scope. Model preferences use a unique owner_scope/scope_type/scope_id/task_type key.

- [ ] Step 5: Run focused tests and commit.

Run: cd backend && pytest -q tests/test_novel_owner_scope.py tests/test_novel_repo.py tests/test_novel_ingestion_service.py

Expected: PASS for scoped CRUD and fresh/old schema migration.

~~~bash
git add backend/app/domain/value_objects.py backend/app/domain/entities/novel.py backend/app/domain/entities/novel_runtime.py backend/app/domain/entities/ai_conversation.py backend/app/domain/repositories/novel_repo.py backend/app/domain/repositories/novel_runtime_repo.py backend/app/domain/repositories/ai_conversation_repo.py backend/app/domain/repositories/novel_model_preference_repo.py backend/app/infrastructure/persistence/sqlite/schema.py backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py backend/app/infrastructure/persistence/sqlite/novel_runtime_repo_impl.py backend/app/infrastructure/persistence/sqlite/ai_conversation_repo_impl.py backend/app/infrastructure/persistence/sqlite/novel_model_preference_repo_impl.py backend/app/infrastructure/persistence/sqlite/bootstrap.py backend/app/infrastructure/persistence/sqlite/novel_db_migrator.py backend/app/database_migrations/novel_schema.sql backend/tests/test_novel_owner_scope.py backend/tests/test_novel_repo.py backend/tests/test_novel_ingestion_service.py
git commit -m "feat: add owner-scoped novel persistence"
~~~

### Task 2: 统一上传、书源和网络链接摄入并持久化续读内容

**Files:**
- Create: backend/app/services/novel_ingestion/__init__.py、parsers.py、url_security.py
- Modify: backend/app/application/services/novel_ingestion_service.py、novel_app_service.py、infrastructure/persistence/factory.py
- Modify: backend/app/database_migrations/novel_schema.sql
- Test: backend/tests/test_novel_import_service.py、test_novel_url_security.py

- [ ] Step 1: Write parser/import failure tests.

~~~python
def test_parser_normalizes_markdown_and_splits_chapters():
    document = NovelDocumentParser().parse(
        filename="story.md",
        media_type="text/markdown",
        data="# 第一章 雨夜\n\n林远走进城门。\n\n# 第二章 清晨\n\n他开始调查。".encode(),
    )
    assert [item.title for item in document.chapters] == ["第一章 雨夜", "第二章 清晨"]
    assert document.chapters[0].text == "林远走进城门。"

@pytest.mark.asyncio
async def test_import_upload_is_idempotent_and_keeps_progress(repo, tmp_path):
    service = NovelIngestionService(repo=repo, source_reader=None, storage_dir=tmp_path)
    first = await service.import_upload("user:1", "story.txt", "text/plain", b"第1章\n正文")
    second = await service.import_upload("user:1", "story.txt", "text/plain", b"第1章\n正文")
    assert first.book_id == second.book_id
    assert second.duplicate is True
    assert await service.get_progress("user:1", first.book_id) is not None
~~~

Run: cd backend && pytest -q tests/test_novel_import_service.py tests/test_novel_url_security.py

Expected: FAIL because parser, progress and URL policy do not exist.

- [ ] Step 2: Implement deterministic document normalization.

Define ParsedChapter and ParsedNovelDocument with ordinal/title/text/content_hash and title/author/normalized_text/chapters/content_hash/media_type. NovelDocumentParser accepts TXT, Markdown, HTML and EPUB only; strips script/style/comment, decodes UTF-8 then GB18030, normalizes whitespace, reuses existing chapter title mapping, and hashes normalized document/chapter text. EPUB is read through zipfile; reject absolute paths, parent traversal, symlinks and archives above the uncompressed limit. Unsupported formats return typed unsupported_format and are not stored.

- [ ] Step 3: Implement secure network and storage boundaries.

NovelUrlPolicy.validate permits only HTTP/HTTPS, rejects credentials, fragments, loopback/link-local/private/multicast/unspecified addresses, localhost and cloud metadata hostnames, and resolves DNS before connecting. fetch caps redirects at 3, response bytes, timeout and content types; revalidates every redirect. Uploaded originals use NOVEL_STORAGE_DIR/<owner_scope_hash>/<content_hash>.<safe_extension>, never the client filename. Configured sources delegate to SourceReadService.search_books/get_book_toc/get_chapter_content and only map results into ParsedChapter.

- [ ] Step 4: Extend NovelIngestionService.

Add:

~~~python
async def import_upload(self, owner_scope: str, filename: str, media_type: str, data: bytes) -> ImportResult: ...
async def import_source(self, owner_scope: str, source_id: int, book_url: str, book_name: str, author: str = "") -> ImportResult: ...
async def import_url(self, owner_scope: str, url: str, title: str = "", author: str = "") -> ImportResult: ...
async def save_progress(self, owner_scope: str, book_id: int, chapter_id: int, offset_chars: int, percent: float, preferences: dict) -> dict: ...
async def get_progress(self, owner_scope: str, book_id: int) -> dict | None: ...
~~~

Each import creates/reuses a scoped NovelBook, stores original metadata separately from normalized chapter text, links NovelIngestion.book_id, queues one analysis task, and returns book ID, duplicate, status and task ID. A failed chapter records its error and does not stop other chapters. Progress validates chapter ownership and clamps percent to 0..1.

- [ ] Step 5: Run import/security tests and commit.

Run: cd backend && pytest -q tests/test_novel_import_service.py tests/test_novel_url_security.py tests/test_novel_ingestion_service.py

Expected: PASS for TXT/Markdown/HTML/EPUB, duplicate content, invalid MIME/extension, ZIP traversal, empty input, progress isolation, private IP, redirect revalidation, response size and source delegation.

~~~bash
git add backend/app/services/novel_ingestion/__init__.py backend/app/services/novel_ingestion/parsers.py backend/app/services/novel_ingestion/url_security.py backend/app/application/services/novel_ingestion_service.py backend/app/application/services/novel_app_service.py backend/app/infrastructure/persistence/factory.py backend/app/database_migrations/novel_schema.sql backend/tests/test_novel_import_service.py backend/tests/test_novel_url_security.py
git commit -m "feat: unify persistent novel imports"
~~~

### Task 3: 接入 Provider 任务路由、模型覆盖和用户隔离缓存

**Files:**
- Modify: backend/app/application/services/provider_platform_service.py、backend/app/infrastructure/providers/base.py、openai_compatible.py、registry.py
- Create: backend/app/application/services/novel_model_selection_service.py、novel_cache_service.py
- Modify: backend/app/infrastructure/persistence/factory.py、bootstrap.py
- Test: backend/tests/test_novel_model_selection.py、test_novel_cache_service.py、test_provider_platform_service.py

- [ ] Step 1: Write precedence/cache tests.

~~~python
def test_model_precedence_is_request_then_session_then_book_then_user_then_route():
    resolver = NovelModelSelectionService(preferences=FakePreferences(), routes=FakeRoutes())
    assert resolver.resolve("user:1", 9, "c1", "chat", "request") == "request"
    assert resolver.resolve("user:1", 9, "c1", "chat", None) == "session"
    assert resolver.resolve("user:1", 9, None, "chat", None) == "book"
    assert resolver.resolve("user:1", None, None, "chat", None) == "user"
    assert resolver.resolve("user:2", 9, None, "chat", None) == "route"

@pytest.mark.asyncio
async def test_cache_key_never_reuses_another_owner_or_knowledge_version():
    cache = NovelCacheService(MemoryCacheProvider())
    first = cache.key(owner_scope="user:1", book_id=9, knowledge_version="k1", model="m", task_type="chat", query="林远是谁", prompt_version="p1", toolset_version="t1")
    second = cache.key(owner_scope="user:2", book_id=9, knowledge_version="k1", model="m", task_type="chat", query="林远是谁", prompt_version="p1", toolset_version="t1")
    third = cache.key(owner_scope="user:1", book_id=9, knowledge_version="k2", model="m", task_type="chat", query="林远是谁", prompt_version="p1", toolset_version="t1")
    assert len({first, second, third}) == 3
~~~

Run: cd backend && pytest -q tests/test_novel_model_selection.py tests/test_novel_cache_service.py tests/test_provider_platform_service.py

Expected: FAIL because only ai/novel routes exist.

- [ ] Step 2: Add route groups and Embedding capability.

Use:

~~~python
PROVIDER_ROUTE_GROUPS = (
    "default", "ai", "source_build", "translation", "novel",
    "novel_chat", "novel_extract", "novel_summary", "novel_embedding",
)
~~~

Add invoke_embedding(model, payload) to ProviderAdapter and implement the OpenAI-compatible /embeddings request. ProviderPlatformService adds invoke_novel_chat/extract/summary/embedding thin wrappers over one private invocation path, accepting owner_scope/model/payload/quota_scope and returning provider/model/attempt/usage/cache metadata. API keys never come from requests. Factory/bootstrap build persisted routes and preserve novel as fallback. ProviderRegistry adds capability filtering over existing selections.

- [ ] Step 3: Implement five-level model selection.

Persist scope_type=user|book|conversation|task preferences keyed by owner_scope and task type. Enforce request_model or session_model or book_model or user_model or route_default. Validate the selected model against the system-open model list for its route group; unknown/disabled models raise ValidationException. AIConversation stores session selection; user/book preferences use the new repository. Return source, provider_group, provider_name, model and redacted route status.

- [ ] Step 4: Implement cache keys, invalidation and usage.

Use this key builder over CacheProvider:

~~~python
def key(self, *, owner_scope, book_id, knowledge_version, model, task_type, query, prompt_version, toolset_version) -> str:
    payload = json.dumps({
        "owner_scope": owner_scope,
        "book_id": book_id,
        "knowledge_version": knowledge_version,
        "model": model,
        "task_type": task_type,
        "query_hash": sha256(query.encode("utf-8")).hexdigest(),
        "prompt_version": prompt_version,
        "toolset_version": toolset_version,
    }, sort_keys=True, separators=(",", ":"))
    return "novel:v1:" + sha256(payload.encode("utf-8")).hexdigest()
~~~

get_or_set caches successful normalized results only; failed calls receive a short retry guard and are not long-lived answers. Add invalidate_book and hit/miss/token/cost counters. Stable prompt prefix is assembled before dynamic query text for DeepSeek/OpenAI-compatible prefix caching without cross-user result sharing.

- [ ] Step 5: Run provider/cache tests and commit.

Run: cd backend && pytest -q tests/test_novel_model_selection.py tests/test_novel_cache_service.py tests/test_provider_platform_service.py tests/test_openai_compatible_provider.py

Expected: PASS for precedence, unavailable model rejection, all novel routes, novel fallback, Embedding payload, owner isolation, knowledge/prompt/tool invalidation, no failed-result caching, usage normalization and masked credentials.

~~~bash
git add backend/app/application/services/provider_platform_service.py backend/app/infrastructure/providers/base.py backend/app/infrastructure/providers/openai_compatible.py backend/app/infrastructure/providers/registry.py backend/app/application/services/novel_model_selection_service.py backend/app/application/services/novel_cache_service.py backend/app/infrastructure/persistence/factory.py backend/app/infrastructure/persistence/sqlite/bootstrap.py backend/tests/test_novel_model_selection.py backend/tests/test_novel_cache_service.py backend/tests/test_provider_platform_service.py backend/tests/test_openai_compatible_provider.py
git commit -m "feat: add novel provider routing and scoped caching"
~~~

### Task 4: 建立可配置 VectorStore 并让 Embedding 真正走 Provider

**Files:**
- Create: backend/app/domain/repositories/vector_store.py
- Create: backend/app/infrastructure/vectorstores/__init__.py、disabled.py、sqlite.py、qdrant.py、pgvector.py
- Modify: backend/app/services/novel_understanding/embedding.py
- Modify: backend/app/infrastructure/persistence/sqlite/schema.py、bootstrap.py、backend/app/database_migrations/novel_schema.sql
- Modify: backend/app/application/services/system_settings_service.py、backend/app/interfaces/http/system.py、factory.py
- Test: backend/tests/test_vector_store.py、test_api_system_settings.py

- [ ] Step 1: Write VectorStore contract tests.

~~~python
@pytest.mark.asyncio
async def test_sqlite_vector_store_filters_owner_book_version(sqlite_vector_store):
    await sqlite_vector_store.upsert([
        VectorRecord("user:1", 7, 1, "k1", [1.0, 0.0], {"text": "甲"}),
        VectorRecord("user:2", 7, 1, "k1", [1.0, 0.0], {"text": "乙"}),
    ])
    results = await sqlite_vector_store.search("user:1", 7, "k1", [1.0, 0.0], top_k=5)
    assert [item.payload["text"] for item in results] == ["甲"]

@pytest.mark.asyncio
async def test_disabled_store_has_no_fake_semantic_hits():
    store = DisabledVectorStore()
    assert (await store.health())["enabled"] is False
    assert await store.search("user:1", 7, "k1", [1.0], top_k=5) == []
~~~

Run: cd backend && pytest -q tests/test_vector_store.py

Expected: FAIL because there is no VectorStore port or configured adapter.

- [ ] Step 2: Define the port and local implementation.

~~~python
@dataclass(frozen=True)
class VectorRecord:
    owner_scope: str
    book_id: int
    chapter_id: int
    knowledge_version: str
    vector: list[float]
    payload: dict[str, Any]

class VectorStore(ABC):
    async def ensure_collection(self, name: str, dimension: int) -> None: ...
    async def upsert(self, records: Sequence[VectorRecord]) -> int: ...
    async def search(self, owner_scope: str, book_id: int, knowledge_version: str, query_vector: list[float], top_k: int) -> list[VectorRecord]: ...
    async def delete_book(self, owner_scope: str, book_id: int, knowledge_version: str | None = None) -> int: ...
    async def health(self) -> dict[str, Any]: ...
~~~

SQLiteVectorStore stores vectors/payloads in local schema with owner/book/version indexes and Python cosine scores. DisabledVectorStore returns no hits and reason. QdrantVectorStore uses existing async httpx, sends owner/book/version filters and validates response shape. PgVectorStore uses injected SQLAlchemy session and raises typed VectorStoreUnavailable if extension/driver is missing. Adapters never receive credentials from request bodies.

- [ ] Step 3: Replace Embedding fallback with Provider routing.

EmbeddingAdapter accepts an EmbeddingProvider callable built from ProviderPlatformService; result records model, dimension, source and cache_hit. Keep local Hash only for deterministic fixtures with semantic=False; RAGRetriever ignores it for vector ranking. Batch calls use one model, honor batch size, cache each text through NovelCacheService, and return typed unavailable when no embedding route exists.

- [ ] Step 4: Add settings and health endpoints.

SystemSettingsService stores vector_backend=disabled|sqlite|qdrant|pgvector, endpoint, collection prefix, credential status, dimension, embedding model, batch size, threshold, concurrency, retries, cache TTL and enabled tool categories. GET /api/system/novel-settings returns safe masked state; PUT validates backend-specific fields; POST /api/system/novel-settings/test-vector-store calls health(). Factory selects the adapter.

- [ ] Step 5: Run vector/config tests and commit.

Run: cd backend && pytest -q tests/test_vector_store.py tests/test_api_system_settings.py tests/test_openai_compatible_provider.py

Expected: PASS for local filters, disabled fallback, Qdrant filters, missing pgvector, Embedding routing, setting validation, secret masking, health and no semantic claim for Hash vectors.

~~~bash
git add backend/app/domain/repositories/vector_store.py backend/app/infrastructure/vectorstores/__init__.py backend/app/infrastructure/vectorstores/disabled.py backend/app/infrastructure/vectorstores/sqlite.py backend/app/infrastructure/vectorstores/qdrant.py backend/app/infrastructure/vectorstores/pgvector.py backend/app/services/novel_understanding/embedding.py backend/app/infrastructure/persistence/sqlite/schema.py backend/app/infrastructure/persistence/sqlite/bootstrap.py backend/app/database_migrations/novel_schema.sql backend/app/application/services/system_settings_service.py backend/app/interfaces/http/system.py backend/app/infrastructure/persistence/factory.py backend/tests/test_vector_store.py backend/tests/test_api_system_settings.py backend/tests/test_openai_compatible_provider.py
git commit -m "feat: add configurable novel vector retrieval"
~~~

### Task 5: 实现增量小说理解、结构化校验和三轨融合

**Files:**
- Modify: backend/app/services/novel_understanding/bm25_index.py、retriever.py、auto_extractor.py
- Create: backend/app/services/novel_understanding/structured_extractor.py、index_service.py
- Modify: backend/app/application/services/novel_agent_service.py、backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py
- Create: backend/app/tasks/novel_index_worker.py; modify backend/app/tasks/scheduler.py
- Test: backend/tests/test_novel_index_service.py、test_rag_retriever.py、test_novel_runtime_service.py

- [ ] Step 1: Write incrementality and evidence tests.

~~~python
@pytest.mark.asyncio
async def test_changed_chapter_is_reindexed_without_reprocessing_unchanged_chapters(index_service):
    first = await index_service.index_book("user:1", book_id=7)
    second = await index_service.index_book("user:1", book_id=7)
    assert first.processed_chapters == 2
    assert second.processed_chapters == 0
    await index_service.repo.update_chapter_content("user:1", chapter_id=2, content="林远与周宁决战")
    assert (await index_service.index_book("user:1", book_id=7)).processed_chapters == 1

@pytest.mark.asyncio
async def test_retrieval_has_source_chapter_confidence_and_evidence(retriever):
    results = await retriever.retrieve("user:1", book_id=7, query="林远为何离开", top_k=5)
    assert all(result.owner_scope == "user:1" for result in results)
    assert all(result.chapter_num >= 0 and result.evidence for result in results)
    assert {result.source for result in results} <= {"bm25", "vector", "kg"}
~~~

Run: cd backend && pytest -q tests/test_novel_index_service.py tests/test_rag_retriever.py

Expected: FAIL because BM25 is not reset/book-scoped, RAGRetriever does not call Embedding/VectorStore and there is no checkpoint service.

- [ ] Step 2: Make BM25 and retrieval scope-safe.

Add BM25Index.clear() and build one index per owner_scope/book_id/knowledge_version. Change RetrievalResult to carry owner_scope, source, item_type, item_id, score, content, book_id, chapter_num, evidence and confidence. Retrieval runs structured exact lookup first for names/counts/relations, BM25 for terms/phrases, VectorStore only with a real semantic embedding, then normalizes scores, merges duplicates and reranks. Every result contains book title, canonical chapter, source type, confidence and bounded evidence; every repository call has scope and book ID.

- [ ] Step 3: Add structured extraction validation and merge rules.

Use a strict Pydantic model with summary, relationships, events, state_changes and arc_tag, ConfigDict(extra=forbid), typed enum/confidence/evidence fields. Reject non-object output, unknown fields, missing evidence chapter IDs, invalid enums, confidence outside 0..1 and evidence text not present in the chapter. Save AutoExtractor results first, normalize aliases, upsert by owner_scope/book/canonical entity, and deduplicate relationships/events by chapter, participants and normalized description. Invoke novel_extract/novel_summary only for complex fields.

- [ ] Step 4: Build checkpoints and background worker.

NovelIndexService.index_book(owner_scope, book_id, from_chapter=None) processes chapters in order, marks state running, saves fingerprint before external calls, persists local results immediately, updates BM25/vector separately and writes completed/failed. If content hash, prompt version, toolset version, embedding model and dimension match, retry skips that chapter. novel_index_worker.py consumes existing NovelAnalysisTask records; scheduler.py only registers this worker and does not duplicate scheduler infrastructure.

- [ ] Step 5: Run index/retrieval tests and commit.

Run: cd backend && pytest -q tests/test_novel_index_service.py tests/test_rag_retriever.py tests/test_novel_runtime_service.py

Expected: PASS for local names/aliases/counts, structured rejection, entity/relation/event/state deduplication, unchanged skip, changed reprocess, failed-chapter continuation, checkpoint retry, BM25/vector/knowledge fallback, evidence and owner/book filters.

~~~bash
git add backend/app/services/novel_understanding/bm25_index.py backend/app/services/novel_understanding/retriever.py backend/app/services/novel_understanding/auto_extractor.py backend/app/services/novel_understanding/structured_extractor.py backend/app/services/novel_understanding/index_service.py backend/app/application/services/novel_agent_service.py backend/app/tasks/novel_index_worker.py backend/app/tasks/scheduler.py backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py backend/tests/test_novel_index_service.py backend/tests/test_rag_retriever.py backend/tests/test_novel_runtime_service.py
git commit -m "feat: add incremental novel understanding index"
~~~

### Task 6: 把现有 NovelAgent、技能注册表和工具审计接入统一上下文服务

**Files:**
- Create: backend/app/application/services/novel_agent_app_service.py
- Modify: backend/app/application/services/novel_agent_service.py、ai_workspace_service.py、agent_runtime_service.py、agent_tool_registry.py
- Modify: backend/app/services/novel_agent/registry.py、agent.py
- Modify: backend/app/infrastructure/persistence/factory.py
- Test: backend/tests/test_novel_agent_app_service.py、test_ai_workspace_service.py、test_agent_runtime_service.py

- [ ] Step 1: Write three-entry and tool tests.

~~~python
@pytest.mark.asyncio
async def test_same_conversation_continues_from_workspace_book_page_and_reader(service):
    conversation = await service.create_conversation("user:1", title="阅读助手", book_id=7, entrypoint="workspace")
    await service.send_message("user:1", conversation["id"], "人物出现次数", entrypoint="workspace")
    await service.send_message("user:1", conversation["id"], "继续分析当前章节", entrypoint="book", chapter_id=2)
    await service.send_message("user:1", conversation["id"], "这段关系有什么证据", entrypoint="reader", chapter_id=2)
    assert len(service.get_conversation("user:1", conversation["id"])["messages"]) == 6
    assert service.platform.calls[-1]["provider_group"] == "novel_chat"

@pytest.mark.asyncio
async def test_cross_owner_operate_tool_is_rejected_and_audited(service):
    with pytest.raises(AuthorizationException):
        await service.call_tool("user:1", "knowledge.propose", {"owner_scope": "user:2"})
    assert service.agent_runtime.history[-1].status == "rejected"
~~~

Run: cd backend && pytest -q tests/test_novel_agent_app_service.py tests/test_ai_workspace_service.py

Expected: FAIL because workspace lacks book/entrypoint context and the existing tool registries have no NovelRepository-backed handlers.

- [ ] Step 2: Add the unified context contract.

Create methods with these signatures, all requiring owner_scope:

~~~python
async def create_conversation(self, owner_scope: str, title: str = "", *, book_id: int | None = None, entrypoint: str = "workspace", model_ref: str | None = None) -> dict: ...
def get_conversation(self, owner_scope: str, conversation_id: str) -> dict: ...
async def send_message(self, owner_scope: str, conversation_id: str, content: str, *, entrypoint: str, book_id: int | None = None, chapter_id: int | None = None, mode: str = "chat", request_model: str | None = None, stream: bool = False) -> dict | AsyncIterator[str]: ...
async def list_tools(self, owner_scope: str, book_id: int | None = None) -> list[dict]: ...
async def call_tool(self, owner_scope: str, tool_name: str, arguments: dict[str, Any], *, book_id: int | None = None, chapter_id: int | None = None, confirmed: bool = False) -> dict: ...
~~~

Context order is book metadata/summary, progress, current chapter, arc/chapter summaries, structured knowledge, hybrid retrieval, conversation summary/recent messages, then question. Workspace can omit a book; book page binds the whole book; reader binds book/chapter/progress. Network/source content is labelled untrusted evidence and cannot become a system instruction.

- [ ] Step 3: Reuse existing registries and add bounded Novel tools.

Register chapter.search, character.profile, character.count, character.aliases, character.relations, plot.timeline, plot.state_changes, world.query, semantic.search, evidence.get, chapter.summary, book.stats and reading.progress through existing ToolRegistry/AgentToolRegistry. Handlers call NovelRepository/RAGRetriever with scope/book. read executes immediately; propose/operate require confirmed and audit. Every call uses AgentRuntimeService run/invocation/result/evidence. Existing source tools and NovelAgent ReAct methods delegate to the same registry/service.

- [ ] Step 4: Add memory, prompt compression and cost records.

Stable prefix contains versioned system rules, Agent identity, tool schemas, book summary and stable world state; dynamic suffix contains question, reading position, retrieval and bounded evidence. Keep recent messages within budget and summarize older messages with a version. Cache summaries, retrieval and final answers. Persist provider/model/input/output/cache/cost through existing AI task/runtime tables; never persist keys or complete untrusted payloads.

- [ ] Step 5: Run Agent/workspace tests and commit.

Run: cd backend && pytest -q tests/test_novel_agent_app_service.py tests/test_ai_workspace_service.py tests/test_agent_runtime_service.py tests/test_novel_agent_core.py tests/test_novel_agent_skills.py

Expected: PASS for three entrypoints, continuation, chapter context, character/relationship/event/evidence tools, permission categories, Prompt Injection isolation, cache hits, model metadata and runtime audit.

~~~bash
git add backend/app/application/services/novel_agent_app_service.py backend/app/application/services/novel_agent_service.py backend/app/application/services/ai_workspace_service.py backend/app/application/services/agent_runtime_service.py backend/app/application/services/agent_tool_registry.py backend/app/services/novel_agent/registry.py backend/app/services/novel_agent/agent.py backend/app/infrastructure/persistence/factory.py backend/tests/test_novel_agent_app_service.py backend/tests/test_ai_workspace_service.py backend/tests/test_agent_runtime_service.py
git commit -m "feat: unify novel agent contexts and tools"
~~~

### Task 7: 暴露认证 API、兼容旧 chat，并接入后台任务

**Files:**
- Modify: backend/app/interfaces/http/deps.py、ai.py、novel.py、system.py
- Modify: backend/app/interfaces/api/v1/novel_agent.py、backend/app/main.py
- Modify: backend/app/infrastructure/persistence/factory.py
- Create: backend/tests/test_api_novel_agent.py
- Modify: backend/tests/test_api_ai_workspace.py、test_api_provider_platform.py

- [ ] Step 1: Write API and compatibility tests.

~~~python
def test_upload_is_scoped_and_legacy_chat_still_works(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.sqlite3"))
    owner = bearer(user_id=1, permissions=["ai.run", "novel.manage"])
    other = bearer(user_id=2, permissions=["ai.run", "novel.manage"])
    created = client.post("/api/v1/novel-agent/import/upload", headers=owner, files={"file": ("a.txt", b"第1章\n甲", "text/plain")})
    assert created.status_code == 200
    book_id = created.json()["data"]["book_id"]
    assert client.get(f"/api/novel/books/{book_id}", headers=other).status_code == 404
    response = client.post("/api/v1/novel-agent/chat", headers=owner, json={"message": "林远是谁"})
    assert response.status_code == 200
    assert response.json()["data"]["answer"]
~~~

Run: cd backend && pytest -q tests/test_api_novel_agent.py tests/test_api_ai_workspace.py

Expected: FAIL because import/session/progress endpoints and authenticated v1 compatibility route do not exist.

- [ ] Step 2: Normalize identities.

Keep RequestIdentity and ApiKeyIdentity and add:

~~~python
def owner_scope_for(identity: RequestIdentity | ApiKeyIdentity) -> str:
    if isinstance(identity, RequestIdentity):
        return str(OwnerScope.user(identity.user_id))
    return str(OwnerScope.api_key(identity.api_key_id))
~~~

Every novel/AI endpoint obtains identity through the current permission dependency and passes owner_scope_for(identity) into application/repository calls. API Key requests use api-key scopes; no endpoint falls back to global scope.

- [ ] Step 3: Add canonical novel endpoints and streams.

Add authenticated endpoints:

~~~text
POST /api/v1/novel-agent/import/upload
POST /api/v1/novel-agent/import/source
POST /api/v1/novel-agent/import/url
GET  /api/novel/books
GET  /api/novel/books/{book_id}
GET  /api/novel/books/{book_id}/chapters
GET  /api/novel/books/{book_id}/knowledge/{kind}
GET  /api/novel/books/{book_id}/progress
PUT  /api/novel/books/{book_id}/progress
POST /api/novel/conversations
GET  /api/novel/conversations/{conversation_id}
POST /api/novel/conversations/{conversation_id}/messages
GET  /api/novel/models
GET  /api/novel/tools
~~~

Message requests accept entrypoint, book_id, chapter_id, mode, model and stream. JSON returns the normalized assistant message. stream returns text/event-stream in order: started, delta, citation, usage, completed or error. Legacy /api/v1/novel-agent/chat creates/continues a scoped conversation and preserves answer/tools_used/iterations/confidence.

- [ ] Step 4: Connect index worker and configuration APIs.

Task status, retry, rebuild and vector health use existing permission groups. Upload enqueues rather than running full analysis in HTTP; worker resumes from NovelIndexState. System settings never accept user Provider credentials.

- [ ] Step 5: Run API tests and commit.

Run: cd backend && pytest -q tests/test_api_novel_agent.py tests/test_api_ai_workspace.py tests/test_api_provider_platform.py tests/test_provider_routing.py

Expected: PASS for permission, three imports, progress, book/chapter/knowledge, stream/non-stream, model restrictions, legacy compatibility and enqueue behavior.

~~~bash
git add backend/app/interfaces/http/deps.py backend/app/interfaces/http/ai.py backend/app/interfaces/http/novel.py backend/app/interfaces/http/system.py backend/app/interfaces/api/v1/novel_agent.py backend/app/main.py backend/app/infrastructure/persistence/factory.py backend/tests/test_api_novel_agent.py backend/tests/test_api_ai_workspace.py backend/tests/test_api_provider_platform.py
git commit -m "feat: expose authenticated novel agent APIs"
~~~

### Task 8: 构建书架、原生阅读器和三入口前端体验

**Files:**
- Modify: frontend/src/api/modules/ai.ts、novel.ts
- Create: frontend/src/features/novel/NovelLibraryPage.tsx、NovelLibraryPage.test.tsx、NovelReaderPage.tsx、NovelReaderPage.test.tsx
- Modify: frontend/src/features/ai/AIWorkspacePage.tsx、AIWorkspacePage.test.tsx
- Modify: frontend/src/app/router.tsx、navigation.tsx

- [ ] Step 1: Write frontend interaction tests.

~~~tsx
test("书架显示进度并能从书源搜索结果加入书架", async () => {
  novelMocks.listNovelBooks.mockResolvedValue(envelope([{ id: 7, book_name: "测试书", progress: 0.42, chapter_title: "第四章" }]))
  novelMocks.searchNovelBooks.mockResolvedValue(envelope([{ bookUrl: "https://source.test/book", name: "远方", author: "作者", sourceId: 3 }]))
  render(<NovelLibraryPage />)
  expect(await screen.findByText("42%")).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("搜索书名"), { target: { value: "远方" } })
  fireEvent.click(screen.getByRole("button", { name: "搜书" }))
  expect(await screen.findByRole("button", { name: "加入书架" })).toBeInTheDocument()
})

test("阅读器把当前章节传给助手", async () => {
  render(<NovelReaderPage />)
  fireEvent.click(await screen.findByRole("button", { name: "问助手" }))
  expect(novelMocks.openAssistant).toHaveBeenCalledWith(expect.objectContaining({ bookId: 7, chapterId: 2, entrypoint: "reader" }))
})
~~~

Run: cd frontend && npm test -- --run src/features/novel/NovelLibraryPage.test.tsx src/features/novel/NovelReaderPage.test.tsx src/features/ai/AIWorkspacePage.test.tsx

Expected: FAIL because APIs and pages do not exist.

- [ ] Step 2: Expand typed API modules.

novel.ts adds listNovelBooks, searchNovelBooks, uploadNovel, importNovelFromSource, importNovelFromUrl, getNovelBook, listNovelChapters, getNovelChapter, getNovelProgress, saveNovelProgress, createNovelConversation, sendNovelMessage, listNovelModels and listNovelTools. ai.ts adds book_id, chapter_id, entrypoint, model and stream. The client never sends or receives API keys; stream parser accepts only documented SSE event names.

- [ ] Step 3: Implement bookshelf.

Reuse ConsoleLayout, Card, Button, Input and Textarea. Show cover fallback, title, author, source, status, percentage/current chapter, updated time, continue/detail/delete/assistant actions. Search calls existing /reading/search adapter; results import by source or URL. Upload accepts TXT/Markdown/HTML/EPUB and displays per-file parse/task errors. No Provider credentials, script fields or raw source rules are rendered.

- [ ] Step 4: Implement reader and shared assistant context.

NovelReaderPage loads scoped book/chapter/progress, saves offset/preferences on chapter changes and debounced scroll, supports paper/night/green themes, custom background, font size, line height and compact/comfortable width. Assistant drawer calls the same conversation service with entrypoint=reader, book_id and chapter_id. AIWorkspacePage uses entrypoint=workspace and book/model selectors; book detail uses entrypoint=book and the same conversation ID.

- [ ] Step 5: Add routes/nav and run frontend tests.

Add /novel/library, /novel/books/:bookId and /novel/books/:bookId/read/:chapterId, keep /ai/workspace and /novel/tasks, and gate with existing novel.manage/ai.run route guards.

Run: cd frontend && npm test -- --run src/features/novel/NovelLibraryPage.test.tsx src/features/novel/NovelReaderPage.test.tsx src/features/ai/AIWorkspacePage.test.tsx && npm run build

Expected: PASS with no TypeScript errors and persistent progress, import states, themes, chapter switching, citations and shared conversations.

~~~bash
git add frontend/src/api/modules/ai.ts frontend/src/api/modules/novel.ts frontend/src/features/novel/NovelLibraryPage.tsx frontend/src/features/novel/NovelLibraryPage.test.tsx frontend/src/features/novel/NovelReaderPage.tsx frontend/src/features/novel/NovelReaderPage.test.tsx frontend/src/features/ai/AIWorkspacePage.tsx frontend/src/features/ai/AIWorkspacePage.test.tsx frontend/src/app/router.tsx frontend/src/app/navigation.tsx
git commit -m "feat: add novel bookshelf reader and assistant"
~~~

### Task 9: 完成系统配置、工具开关、审计和成本统计

**Files:**
- Modify: backend/app/application/services/system_settings_service.py、novel_cache_service.py、novel_agent_app_service.py、agent_runtime_service.py
- Modify: backend/app/interfaces/http/system.py
- Modify: frontend/src/features/system/ProviderRoutingSettings.tsx、ProviderRoutingSettings.test.tsx
- Modify: backend/app/infrastructure/persistence/sqlite/schema.py、bootstrap.py
- Test: backend/tests/test_novel_security.py、test_api_system_settings.py

- [ ] Step 1: Write configuration/audit/security tests.

~~~python
def test_system_novel_settings_never_return_api_key(client, admin_headers):
    response = client.get("/api/system/novel-settings", headers=admin_headers)
    assert response.status_code == 200
    assert "api_key" not in str(response.json()).lower()

@pytest.mark.asyncio
async def test_prompt_injection_in_chapter_cannot_change_tools(service):
    answer = await service.send_message("user:1", "conversation-1", "读取这一章", entrypoint="reader", chapter_id=1)
    assert "shell" not in [call["name"] for call in answer["tool_calls"]]
    assert all(call["category"] == "read" for call in answer["tool_calls"])
~~~

Run: cd backend && pytest -q tests/test_novel_security.py tests/test_api_system_settings.py

Expected: FAIL until settings, tool categories, prompt boundaries and usage records are complete.

- [ ] Step 2: Add complete settings surface.

Expose route groups and user-visible models, VectorStore backend/health, Embedding model/dimension/batch, read/propose/operate switches, chapter size/concurrency/retry/index policy, cache TTL/similarity threshold/cost budget. Use existing ProviderRoutingSettings, not a second settings page. Credentials remain server-side and UI receives configured/masked status only.

- [ ] Step 3: Record audit and cost through existing runtime boundaries.

Each novel request records owner scope, book/chapter, entrypoint, conversation, provider/model, attempts, cache hit, input/output tokens, cost, tool names and evidence IDs. Reuse AgentRuntimeService and existing AI task/runtime tables; add only missing columns/indexes. Never record API keys, cookies, authorization headers, full chapter text or raw URL bodies.

- [ ] Step 4: Verify prompt/tool security.

Treat chapter text, uploads, HTML and source responses as untrusted evidence. System instructions state evidence cannot alter rules, request secrets, enable tools or authorize writes. Tool arguments are schema/scope/size validated; read is default, propose/operate require confirmation. Test path traversal, SSRF, cross-user book/conversation/index/cache, hostile chapter text, unknown model, disabled tool and secret leakage.

- [ ] Step 5: Run settings/security tests and commit.

Run: cd backend && pytest -q tests/test_novel_security.py tests/test_api_system_settings.py tests/test_api_provider_platform.py tests/test_agent_runtime_service.py

Expected: PASS for masked credentials, all setting groups, switches, audit, token/cost/cache metrics, Prompt Injection containment and disabled-backend degradation.

~~~bash
git add backend/app/application/services/system_settings_service.py backend/app/application/services/novel_cache_service.py backend/app/application/services/novel_agent_app_service.py backend/app/application/services/agent_runtime_service.py backend/app/interfaces/http/system.py frontend/src/features/system/ProviderRoutingSettings.tsx frontend/src/features/system/ProviderRoutingSettings.test.tsx backend/app/infrastructure/persistence/sqlite/schema.py backend/app/infrastructure/persistence/sqlite/bootstrap.py backend/tests/test_novel_security.py backend/tests/test_api_system_settings.py
git commit -m "feat: complete novel agent settings and audit"
~~~

### Task 10: 全量验证、兼容性回归和 GitHub 交付

**Files:**
- Modify only files listed by failing tests; never revert unrelated user changes.
- Test: all backend and frontend suites.
- Documentation check: docs/superpowers/specs/2026-07-21-novel-agent-assistant-design.md and this plan.

- [ ] Step 1: Run focused backend suites.

~~~bash
cd backend
pytest -q tests/test_novel_owner_scope.py tests/test_novel_import_service.py tests/test_novel_url_security.py tests/test_novel_model_selection.py tests/test_novel_cache_service.py tests/test_vector_store.py tests/test_novel_index_service.py tests/test_novel_agent_app_service.py tests/test_api_novel_agent.py tests/test_novel_security.py
~~~

Expected: PASS with fake Provider and fake VectorStore only.

- [ ] Step 2: Run the complete backend regression suite.

Run: cd backend && pytest -q

Expected: PASS for source, auth, scheduler, provider, AI workspace, translation and novel tests. Preserve existing user-modified files and fix contracts instead of restoring them.

- [ ] Step 3: Run the complete frontend suite and build.

~~~bash
cd frontend
npm test -- --run
npm run build
~~~

Expected: all Vitest tests pass and tsc -b && vite build completes without type errors.

- [ ] Step 4: Run acceptance/security smoke checks.

~~~text
1. user:1 uploads, closes the web session, returns, sees the same book/progress and continues.
2. user:1 imports one configured source book and one permitted HTTPS page.
3. user:1 asks for character count, relation, timeline and chapter evidence.
4. The same conversation continues from workspace, book page and reader.
5. Request/session/book/user/route model precedence appears in usage metadata.
6. user:1 hits only user:1 cache entries; user:2 receives a miss.
7. Disabling VectorStore still returns BM25/structured results.
8. Changing one chapter reindexes only that chapter.
9. Provider/route/tool/vector health and token/cost/cache metrics are visible in settings.
10. Private URL, path traversal, malicious EPUB, hostile chapter instructions and unauthorized tools are rejected.
~~~

Expected: all ten checks pass, with no API key or cross-user content in responses/audit.

- [ ] Step 5: Review diff, commit implementation changes and push.

~~~bash
git status --short
git diff --check
git diff --stat origin/feat/source-import-rule-center...HEAD
git log --oneline --decorate -12
git push origin feat/source-import-rule-center
~~~

Expected: diff check is clean; feature commits contain only intentional implementation files. .vite/, backend/.venv-linux/, the deleted 测试源/shareBookSource.json, the GBK/乱码 directory and unrelated pre-existing changes are not staged or pushed.

## 计划自审

- 规格覆盖：Task 1 covers formal models, owner_scope, index state and migration; Task 2 covers upload/source/URL ingestion, parsing, storage and continuation; Task 3 covers model precedence, Provider route groups, DeepSeek-compatible prefix order, cache isolation and cost; Task 4 covers configurable VectorStore and Provider-backed Embedding; Task 5 covers local entities/aliases/counts, relationships/events/states, incremental checkpoints and hybrid retrieval; Task 6 covers shared Agent context, memory, tools, evidence and three entrypoints; Task 7 covers authenticated APIs, streaming, tasks and legacy compatibility; Task 8 covers bookshelf, search, imports, reader, themes and shared assistant; Task 9 covers settings, permissions, audit, Prompt Injection and secret handling; Task 10 covers regression and acceptance.
- 占位检查：计划不含未完成标记；每个任务都有文件、失败测试、实现契约、命令、预期结果和提交边界。
- 类型一致性：OwnerScope.value、NovelRepository 的 scope-first 方法、VectorRecord、RetrievalResult、NovelAgentAppService 方法签名、Provider route group 名称和前端 API 字段在后续任务中保持同一命名。
