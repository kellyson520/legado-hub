# 小说 Agent 分析提速与绑定修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复已绑定小说会话的上下文丢失，并通过复用 Agent/RAG、修正无编号章节、批量持久化和批量向量处理缩短小说分析等待时间。

**Architecture:** 保留现有 `NovelAgentAppService`、`RAGRetriever`、`NovelRepository` 和 `NovelIndexWorker`，只在 HTTP 依赖层增加进程内共享装配，在应用服务层按会话是否绑定书籍选择统一 Agent 或旧兼容链路。索引服务负责章节选择、增量状态和阶段计时，仓储负责一次事务内批量写入，Worker 根据索引结果更新任务和书籍状态。

**Tech Stack:** Python 3.12, FastAPI, pytest/pytest-asyncio, aiosqlite, SQLite WAL, SQLAlchemy, asyncio, 现有 ProviderPlatformService、EmbeddingAdapter、VectorStore。

---

## 文件边界

- Modify: `backend/app/interfaces/http/ai.py` — 为 AI Workspace 对话接口注入共享小说 Agent。
- Modify: `backend/app/interfaces/http/novel.py` — 缓存同一进程的小说仓储、RAGRetriever 和 NovelAgentAppService，并提供测试重置入口。
- Modify: `backend/app/infrastructure/persistence/factory.py` — 允许 Workspace 接收已装配的 NovelAgentAppService。
- Modify: `backend/app/application/services/ai_workspace_service.py` — 混合处理已绑定小说会话和未绑定旧会话；绑定会话省略 `book_id` 时继续使用持久化绑定。
- Modify: `backend/app/interfaces/api/v1/novel_agent.py` — 兼容聊天入口复用共享小说 Agent。
- Test: `backend/tests/test_ai_workspace_service.py`, `backend/tests/test_api_ai.py`, `backend/tests/test_api_novel_agent.py` — 覆盖入口路由、绑定继承和旧会话兼容。
- Modify: `backend/app/domain/repositories/novel_repo.py` — 章节查询默认从 `canonical_num=0` 开始。
- Modify: `backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py` — 支持编号 0，并把实体、关系、事件、状态批量方法改为单事务写入。
- Modify: `backend/app/services/novel_understanding/index_service.py` — 处理编号 0、返回明确阶段状态、批量持久化、一次向量健康检查/Embedding/upsert，并记录阶段耗时。
- Modify: `backend/app/tasks/novel_index_worker.py` — 保存状态和计时结果，并把索引结果映射到书籍状态。
- Test: `backend/tests/test_novel_repo.py`, `backend/tests/test_novel_index_service.py`, `backend/tests/test_novel_index_worker.py` — 覆盖编号 0、批量写入、空任务、部分失败和状态更新。

执行时只暂存上述任务涉及的文件；工作区中已有的 `scheduler.py`、审计报告、前端构建缓存、测试目录和删除文件不进入这些提交。

### Task 1: 为入口绑定和共享装配补充失败测试

**Files:**
- Modify: `backend/tests/test_ai_workspace_service.py`
- Modify: `backend/tests/test_api_ai.py`
- Modify: `backend/tests/test_api_novel_agent.py`

- [ ] **Step 1: 写出未绑定会话仍走旧 Workspace 的失败测试**

在 `test_ai_workspace_service.py` 增加以下行为测试。它向带有 `novel_agent_app` 的 Workspace 创建一个未绑定的普通对话；当前实现会无条件委托 NovelAgent，因此测试应失败。

```python
@pytest.mark.asyncio
async def test_workspace_keeps_unbound_workspace_conversation_on_legacy_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "workspace-legacy-dispatch.sqlite3"))

    from app.application.services.ai_workspace_service import AIWorkspaceService
    from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    class NovelAgentProbe:
        def __init__(self):
            self.calls = []

        async def create_conversation(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"id": "must-not-be-used"}

    bootstrap_sqlite()
    probe = NovelAgentProbe()
    service = AIWorkspaceService(
        RecordingPlatform(),
        SQLiteAIConversationRepository(),
        SourceRepository(),
        TaskRepository(),
        AuditRepository(),
        novel_agent_app=probe,
    )

    conversation = await service.create_conversation("7", "普通工作台")

    assert conversation["id"] != "must-not-be-used"
    assert probe.calls == []
```

- [ ] **Step 2: 写出 `/api/ai` 注入共享 Agent 的失败测试**

在 `test_api_ai.py` 增加一个使用测试 Token 的路由测试。测试用 `raising=False` 兼容当前模块尚未导出依赖函数的状态；当前路由不会调用共享依赖，也不会向工厂传入 `novel_agent_app`，因此最后一个断言应失败。

```python
def test_ai_conversation_route_injects_shared_novel_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ai-novel-agent.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.interfaces.http import ai as ai_http
    from app.main import app

    sentinel = object()
    captured = {}

    async def shared_agent():
        return sentinel

    class Workspace:
        async def create_conversation(self, *args, **kwargs):
            return {"id": "conversation-1", "book_id": kwargs["book_id"]}

    def workspace_builder(*_args, novel_agent_app=None, **_kwargs):
        captured["novel_agent_app"] = novel_agent_app
        return Workspace()

    monkeypatch.setattr(ai_http, "get_novel_agent_app_service", shared_agent, raising=False)
    monkeypatch.setattr(ai_http, "build_ai_workspace_service", workspace_builder)
    token = create_access_token({"sub": "1", "permissions": ["ai.run"]})

    from fastapi.testclient import TestClient

    response = TestClient(app).post(
        "/api/ai/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "书籍助手", "book_id": 8, "entrypoint": "book"},
    )

    assert response.status_code == 200
    assert captured["novel_agent_app"] is sentinel
```

- [ ] **Step 3: 写出兼容聊天入口复用共享服务的失败测试**

在 `test_api_novel_agent.py` 保留现有上传和聊天测试，并补充断言：把 `novel_http.get_novel_agent_app_service` 替换为记录调用的异步工厂，调用 `/api/v1/novel-agent/chat` 时必须使用该工厂。当前兼容入口直接调用 `build_novel_agent_app_service()`，所以测试应失败。

```python
def test_compat_chat_uses_shared_novel_agent_dependency(monkeypatch):
    from app.interfaces.api.v1 import novel_agent as novel_agent_api

    class Agent:
        def __init__(self):
            self.calls = 0

        async def create_conversation(self, *args, **kwargs):
            self.calls += 1
            return {"id": "shared-conversation"}

        async def send_message(self, *args, **kwargs):
            self.calls += 1
            return {"content": "共享答案", "tool_calls": []}

    agent = Agent()

    async def shared_agent():
        return agent

    monkeypatch.setattr(novel_agent_api.novel_http, "get_novel_agent_app_service", shared_agent)
    monkeypatch.setattr(
        novel_agent_api,
        "build_novel_agent_app_service",
        lambda: (_ for _ in ()).throw(AssertionError("compat chat used the non-shared builder")),
    )

    from app.main import app

    response = TestClient(app).post(
        "/api/v1/novel-agent/chat",
        headers=_headers(1, ["ai.run"]),
        json={"message": "这本书写得怎么样", "book_id": 8},
    )

    assert response.status_code == 200
    assert agent.calls >= 1
```

- [ ] **Step 4: 运行这些测试并确认它们因缺少装配/分流而失败**

Run:

```bash
cd /root/legado-hub/backend
.venv-linux/bin/python -m pytest tests/test_ai_workspace_service.py::test_workspace_keeps_unbound_workspace_conversation_on_legacy_path tests/test_api_ai.py::test_ai_conversation_route_injects_shared_novel_agent tests/test_api_novel_agent.py::test_compat_chat_uses_shared_novel_agent_dependency -q
```

Expected: FAIL，至少包含“未绑定普通会话被 NovelAgent 接管”和“`novel_agent_app` 未注入”两类断言失败；如果出现导入错误，先修正测试导入路径后重跑，不能把导入错误当作红灯依据。

### Task 2: 实现共享 Agent/RAG 装配和绑定分流

**Files:**
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/interfaces/http/novel.py`
- Modify: `backend/app/interfaces/http/ai.py`
- Modify: `backend/app/application/services/ai_workspace_service.py`
- Modify: `backend/app/interfaces/api/v1/novel_agent.py`
- Test: `backend/tests/test_ai_workspace_service.py`, `backend/tests/test_api_ai.py`, `backend/tests/test_api_novel_agent.py`

- [ ] **Step 1: 给工厂增加可选的已装配小说 Agent 参数**

把 `build_ai_workspace_service` 改为接受关键字参数，并把参数原样传给 `AIWorkspaceService`；无参数时仍保留旧调用兼容性。

```python
def build_ai_workspace_service(*, novel_agent_app=None) -> AIWorkspaceService:
    bootstrap_sqlite()
    return AIWorkspaceService(
        platform=build_provider_platform_service(),
        conversations=SQLiteAIConversationRepository(),
        sources=build_source_runtime_repository(),
        ai_tasks=build_ai_runtime_repository(),
        audit=build_auth_repository(),
        novel_agent_app=novel_agent_app,
    )
```

- [ ] **Step 2: 在 HTTP 小说依赖中缓存同一进程的 RAG 和 Agent**

在 `backend/app/interfaces/http/novel.py` 的模块级依赖区域增加 `_novel_agent_app_cache` 和 `_novel_agent_repo_cache`。第一次调用时复用已有 `get_novel_repository()`、`RAGRetriever` 和 `build_novel_agent_app_service`; 后续调用只返回同一对象。缓存以仓储对象身份作为边界，避免测试或进程切换数据库后误用旧实例。

实现必须保持以下契约：

```python
_novel_agent_app_cache = None
_novel_agent_repo_cache = None


async def get_novel_agent_app_service():
    global _novel_agent_app_cache, _novel_agent_repo_cache
    repo = await get_scoped_novel_repository()
    if _novel_agent_app_cache is None or _novel_agent_repo_cache is not repo:
        novel_settings = build_system_settings_service().get_novel_settings()
        retriever = RAGRetriever(
            repo,
            vector_store=build_vector_store(),
            similarity_threshold=float(novel_settings.get("threshold", 0.0) or 0.0),
        )
        _novel_agent_app_cache = _build_novel_agent_app_service(
            novel_repo=repo,
            retriever=retriever,
        )
        _novel_agent_repo_cache = repo
    return _novel_agent_app_cache


def reset_novel_agent_app_service_cache() -> None:
    global _novel_agent_app_cache, _novel_agent_repo_cache
    _novel_agent_app_cache = None
    _novel_agent_repo_cache = None
```

HTTP 路由生产代码不调用 reset；测试在 monkeypatch 数据库或依赖后调用它，避免跨测试复用。

- [ ] **Step 3: 让 `/api/ai` 的对话路由注入共享 Agent**

在 `backend/app/interfaces/http/ai.py` 导入 `get_novel_agent_app_service`，增加异步 Workspace 工厂，并把对话列表、创建、详情和消息四个路由改为 `await get_ai_workspace_service()`。

```python
async def get_ai_workspace_service() -> AIWorkspaceService:
    return build_ai_workspace_service(
        novel_agent_app=await get_novel_agent_app_service(),
    )
```

`/api/ai/tasks` 和 `/api/ai/tasks/character` 保持旧 AIService 路径，不为不相关的任务强制初始化小说数据库。

- [ ] **Step 4: 在 Workspace 中按上下文选择链路**

调整 `AIWorkspaceService` 的分流规则：

1. 新建会话只有在 `book_id` 非空或入口为 `book`/`reader` 时委托 NovelAgent；普通 `workspace` 且无书籍继续写入旧会话。
2. 列表合并旧 actor id 和 NovelAgent 的 owner-scope actor id，按会话 id 去重，避免已绑定会话从 `/api/ai/conversations` 消失。
3. 详情先尝试 NovelAgent；找不到绑定会话再走旧仓储；旧会话不得因为共享 Agent 已注入而返回“小说会话不存在”。
4. 发送消息在显式指定书籍、`book`/`reader` 入口或持久化会话已绑定书籍时委托 NovelAgent。省略单次 `book_id` 时传入 `None`，由现有 `NovelAgentAppService.send_message` 从 `conversation.book_id` 继承并校验 owner scope。
5. 未绑定旧会话仍执行原有书源工具和 AI Provider 工具循环。

不要复制 `NovelAgentAppService` 的上下文构建逻辑；只在 Workspace 做选择和转发。

- [ ] **Step 5: 让兼容 `/api/v1/novel-agent/chat` 使用同一依赖**

将 `compat_chat` 中的 `build_novel_agent_app_service()` 替换为 `await novel_http.get_novel_agent_app_service()`；无书籍旧请求仍由统一服务处理，但共享相同会话仓储和 RAG 缓存。

- [ ] **Step 6: 运行红灯测试并确认全部变绿**

Run:

```bash
cd /root/legado-hub/backend
.venv-linux/bin/python -m pytest tests/test_ai_workspace_service.py tests/test_api_ai.py tests/test_api_novel_agent.py -q
```

Expected: PASS，且原有未绑定 Workspace 工具测试仍使用 `provider_group="ai"`；绑定会话测试能看到小说上下文。

- [ ] **Step 7: 提交入口修复**

```bash
cd /root/legado-hub
git add backend/app/infrastructure/persistence/factory.py backend/app/interfaces/http/novel.py backend/app/interfaces/http/ai.py backend/app/application/services/ai_workspace_service.py backend/app/interfaces/api/v1/novel_agent.py backend/tests/test_ai_workspace_service.py backend/tests/test_api_ai.py backend/tests/test_api_novel_agent.py
git commit -m "fix: route bound novel conversations through shared agent"
```

### Task 3: 为编号 0、空索引和任务状态补充失败测试

**Files:**
- Modify: `backend/tests/test_novel_repo.py`
- Modify: `backend/tests/test_novel_index_service.py`
- Modify: `backend/tests/test_novel_index_worker.py`

- [ ] **Step 1: 验证默认章节查询包含 `canonical_num=0`**

在 `test_novel_repo.py` 增加单章序章测试：保存 `canonical_full="P0"`, `canonical_num=0`，调用带 owner scope 的 `get_chapters_by_book` 不传 `start_num`，断言得到该章节。

```python
@pytest.mark.asyncio
async def test_get_chapters_by_book_includes_un_numbered_chapter_zero(repo):
    book = await repo.save_book("user:1", NovelBook(book_url="https://zero.test", book_name="无编号书"))
    await repo.save_chapter(
        "user:1",
        NovelChapter(book_id=book.id, canonical_full="P0", canonical_num=0, raw_text="正文"),
    )

    chapters = await repo.get_chapters_by_book("user:1", book.id)

    assert [chapter.canonical_num for chapter in chapters] == [0]
```

- [ ] **Step 2: 验证单章编号 0 会完成索引并更新书籍**

在 `test_novel_index_service.py` 使用已有 `index_service` fixture 增加一个编号 0 章节，断言它被处理并完成书籍状态更新。当前实现会得到 0 章并保持原状态，因此应失败。

```python
@pytest.mark.asyncio
async def test_canonical_zero_chapter_is_indexed_and_book_becomes_ready(index_service):
    from app.domain.entities.novel import NovelChapter, NovelStatus

    service, book_id = index_service
    await service.repo.save_chapter(
        "user:1",
        NovelChapter(
            book_id=book_id,
            canonical_full="P0",
            canonical_num=0,
            chapter_title="上传正文",
            raw_text="林远在雨夜进入青云宗。",
        ),
    )

    result = await service.index_book("user:1", book_id)

    assert result.processed_chapters == 3
    assert result.status == "succeeded"
    assert (await service.repo.get_book_by_id("user:1", book_id)).status == NovelStatus.READY
    assert (await service.repo.get_book_by_id("user:1", book_id)).ingest_progress == 1.0
```

- [ ] **Step 3: 验证空书不再伪装成成功**

在 `test_novel_index_service.py` 增加以下测试：

```python
@pytest.mark.asyncio
async def test_empty_book_is_not_reported_as_success(index_service):
    from app.domain.entities.novel import NovelStatus, NovelBook

    service, _ = index_service
    book = await service.repo.save_book(
        "user:1", NovelBook(book_url="https://empty.test", book_name="空书")
    )

    result = await service.index_book("user:1", book.id)

    assert result.succeeded is False
    assert result.status == "empty"
    assert result.errors[0]["reason"] == "no_chapters"
    assert (await service.repo.get_book_by_id("user:1", book.id)).status == NovelStatus.ERROR
```

- [ ] **Step 4: 验证 Worker 保存明确任务状态**

扩展 `test_novel_index_worker.py` 的假 IndexService，让它返回以下结果对象；断言任务状态为 `empty`，结果包含 `status`、`errors` 和 `timings_ms`。当前 Worker 固定把 `failed_chapters == 0` 映射成 `succeeded`，因此应失败。

```python
return type(
    "IndexResult",
    (),
    {
        "status": "empty",
        "selected_chapters": 0,
        "processed_chapters": 0,
        "skipped_chapters": 0,
        "failed_chapters": 0,
        "errors": [{"reason": "no_chapters"}],
        "timings_ms": {"total": 0.1},
    },
)()
```

- [ ] **Step 5: 运行测试确认红灯**

Run:

```bash
cd /root/legado-hub/backend
.venv-linux/bin/python -m pytest tests/test_novel_repo.py::test_get_chapters_by_book_includes_un_numbered_chapter_zero tests/test_novel_index_service.py tests/test_novel_index_worker.py -q
```

Expected: 新增编号 0、状态属性和空任务断言失败；现有 5 个索引回归测试继续显示其原有结果。

### Task 4: 修复章节选择、状态收敛和 Worker 结果

**Files:**
- Modify: `backend/app/domain/repositories/novel_repo.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py`
- Modify: `backend/app/services/novel_understanding/index_service.py`
- Modify: `backend/app/tasks/novel_index_worker.py`
- Test: `backend/tests/test_novel_repo.py`, `backend/tests/test_novel_index_service.py`, `backend/tests/test_novel_index_worker.py`

- [ ] **Step 1: 把章节查询默认下限改为 0**

同步抽象接口和 SQLite 实现的 `get_chapters_by_book(..., start_num=0)` 默认值；SQL 仍使用参数化的 `canonical_num >= ?`，不得把 0 特判成字符串或绕过 owner scope。`NovelIndexService._chapters` 使用：

```python
start = max(0, int(from_chapter)) if from_chapter is not None else 0
```

显式 `from_chapter=1` 仍只索引正章；显式 `from_chapter=0` 包含序章和无编号上传章节。

- [ ] **Step 2: 增加可判定的 IndexResult 状态**

在 `IndexResult` 增加 `selected_chapters: int`, `no_chapters: bool` 和 `timings_ms: dict[str, float]`，并实现以下确定性状态：

```python
@property
def status(self) -> str:
    if self.no_chapters:
        return "empty"
    if self.failed_chapters and (self.processed_chapters or self.skipped_chapters):
        return "partial"
    if self.failed_chapters:
        return "failed"
    return "succeeded"

@property
def succeeded(self) -> bool:
    return self.status == "succeeded"
```

章节列表为空时设置 `no_chapters=True`、`errors=[{"reason": "no_chapters", "message": "no chapters available for indexing"}]`，不能返回普通成功结果。

- [ ] **Step 3: 在索引结束时更新书籍状态**

在 `index_book` 的所有章节处理完成后调用已有 `repo.update_book_status`：

- `succeeded`: `NovelStatus.READY`, progress `1.0`, 清空错误。
- `partial`: `NovelStatus.READY`, progress `(processed_chapters + skipped_chapters) / selected_chapters`，错误保存失败章节数量和 `errors` 中的首个原因。
- `empty` 或 `failed`: `NovelStatus.ERROR`，progress 保持当前值，错误信息分别为无章节或失败原因。

使用 `max(0, min(1, value))` 限制进度，并保留 owner scope。书籍状态更新异常要追加到 `result.errors`、递增 `failed_chapters` 并把结果状态保留为失败，不能吞掉数据库错误。

- [ ] **Step 4: 让 Worker 使用 IndexResult.status**

Worker 不再根据 `failed_chapters == 0` 猜测成功，改为保存：

```python
task.status = indexed.status
task.result = {
    "status": indexed.status,
    "selected_chapters": indexed.selected_chapters,
    "processed_chapters": indexed.processed_chapters,
    "skipped_chapters": indexed.skipped_chapters,
    "failed_chapters": indexed.failed_chapters,
    "errors": indexed.errors,
    "timings_ms": indexed.timings_ms,
}
```

`NovelAnalysisTask` 的状态字段是字符串，不需要新增第二套枚举；已有 `queued`、`running`、`succeeded`、`partial`、`failed` 兼容继续保留，空数据使用明确的 `empty`。

同步更新现有成功 Worker Fixture，使其返回 `status="succeeded"`、`selected_chapters=2` 和 `timings_ms={"total": 0.1}`；这样旧的成功路径也验证新的结果契约，而不是依靠动态属性缺失。

- [ ] **Step 5: 运行 Task 3 测试确认变绿**

Run:

```bash
cd /root/legado-hub/backend
.venv-linux/bin/python -m pytest tests/test_novel_repo.py tests/test_novel_index_service.py tests/test_novel_index_worker.py -q
```

Expected: PASS，编号 0 至少处理 1 章，重复索引仍只增加 `skipped_chapters`，空书任务不是 `succeeded`。

- [ ] **Step 6: 提交索引状态修复**

```bash
cd /root/legado-hub
git add backend/app/domain/repositories/novel_repo.py backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py backend/app/services/novel_understanding/index_service.py backend/app/tasks/novel_index_worker.py backend/tests/test_novel_repo.py backend/tests/test_novel_index_service.py backend/tests/test_novel_index_worker.py
git commit -m "fix: index unnumbered novel chapters and finalize status"
```

### Task 5: 为批量持久化和阶段性能补充失败测试

**Files:**
- Modify: `backend/tests/test_novel_repo.py`
- Modify: `backend/tests/test_novel_index_service.py`

- [ ] **Step 1: 写出四类仓储批量方法不调用单条方法的测试**

在真实 `SqliteNovelRepository` 子类中覆盖 `save_entity`、`save_relationship`、`save_event`、`save_state_change` 为抛出 `AssertionError` 的方法；分别调用四个 `*_batch` 方法。当前批量实现内部循环调用单条方法，测试应失败；真正的批量 SQL 实现会通过。

```python
@pytest.mark.asyncio
async def test_batch_knowledge_writes_use_one_batch_path_without_single_row_calls(repo):
    book = await repo.save_book("user:1", NovelBook(book_url="https://batch.test", book_name="批量书"))

    async def unexpected_single_row(*_args, **_kwargs):
        raise AssertionError("single-row persistence must not be used by batch methods")

    repo.save_entity = unexpected_single_row
    repo.save_relationship = unexpected_single_row
    repo.save_event = unexpected_single_row
    repo.save_state_change = unexpected_single_row

    assert await repo.save_entities_batch(
        "user:1", [NovelEntity(book_id=book.id, name="甲")]
    ) == 1
    assert await repo.save_relationships_batch(
        "user:1", [NovelRelationship(book_id=book.id, source_entity="甲", target_entity="乙")]
    ) == 1
    assert await repo.save_events_batch(
        "user:1", [NovelEvent(book_id=book.id, chapter_id=1, chapter_num=1, description="相遇")]
    ) == 1
    assert await repo.save_state_changes_batch(
        "user:1", [NovelStateChange(book_id=book.id, entity_name="甲", chapter_id=1, chapter_num=1)]
    ) == 1
```

- [ ] **Step 2: 写出 IndexService 优先调用批量接口的测试**

用现有 `SqliteNovelRepository` 子类覆盖四个单条方法为失败方法，用一个提取 Fixture 返回一条实体和一条关系；直接批量方法的测试已经覆盖事件/状态，IndexService 测试验证它不会退回单条路径。

```python
@pytest.mark.asyncio
async def test_index_service_prefers_batch_persistence(index_service):
    from app.domain.entities.novel import NovelEntity, NovelRelationship, RelationType
    from app.infrastructure.vectorstores.disabled import DisabledVectorStore
    from app.services.novel_understanding.embedding import EmbeddingAdapter
    from app.services.novel_understanding.index_service import NovelIndexService

    base, book_id = index_service

    async def unexpected_single_row(*_args, **_kwargs):
        raise AssertionError("index service used single-row persistence")

    base.save_entity = unexpected_single_row
    base.save_relationship = unexpected_single_row

    class Extractor:
        def extract_from_chapter(self, current_book_id, chapter_num, _title, _text):
            return {
                "entities": [NovelEntity(book_id=current_book_id, name="林远")],
                "relationships": [
                    NovelRelationship(
                        book_id=current_book_id,
                        source_entity="林远",
                        target_entity="周宁",
                        relation_type=RelationType.ALLY,
                        since_chapter=chapter_num,
                    )
                ],
            }

        @staticmethod
        def merge_entities(entities):
            return entities

    service = NovelIndexService(
        repo=base,
        extractor=Extractor(),
        vector_store=DisabledVectorStore(),
        embedding=EmbeddingAdapter(),
    )

    result = await service.index_book("user:1", book_id)

    assert result.status == "succeeded"
    assert len(await base.list_entities("user:1", book_id)) >= 1
    assert len(await base.get_relationships("user:1", book_id, limit=100)) >= 1
```

- [ ] **Step 3: 写出向量健康检查、Embedding 和 upsert 批量化的测试**

构造两个章节、一个 `VectorStore` 记录 `health_calls` 和 `upsert_calls`，一个提供 `embed_batch` 的假 Embedding。断言：

```python
assert vector_store.health_calls == 1
assert embedding.batch_calls == [["第一章正文", "第二章正文"]]
assert [len(batch) for batch in vector_store.upsert_calls] == [2]
```

同时断言 `result.timings_ms` 至少包含 `bm25`、`extract`、`persist`、`vector`、`total` 五个非负数。当前实现逐章健康检查、逐章 Embedding/upsert，且没有计时字段，应失败。

- [ ] **Step 4: 运行红灯测试**

Run:

```bash
cd /root/legado-hub/backend
.venv-linux/bin/python -m pytest tests/test_novel_repo.py::test_batch_knowledge_writes_use_one_batch_path_without_single_row_calls tests/test_novel_index_service.py -q
```

Expected: 单条调用保护和向量调用次数断言失败；不要因为已有索引测试通过而跳过红灯确认。

### Task 6: 实现批量 SQLite 写入、批量索引和计时

**Files:**
- Modify: `backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py`
- Modify: `backend/app/services/novel_understanding/index_service.py`
- Test: `backend/tests/test_novel_repo.py`, `backend/tests/test_novel_index_service.py`

- [ ] **Step 1: 把四个批量仓储方法改成单事务 SQL**

每个批量方法遵守相同顺序：空列表直接返回 0；按 owner scope 调用 `_require_book` 检查每个不同 `book_id`；使用 `executemany` 写入；只执行一次 `commit`；返回输入数量。实体使用现有 `ON CONFLICT(book_id, name) DO UPDATE` 语义，关系/事件/状态保持现有字段和 JSON 序列化语义。

实体批量 SQL 的字段和冲突更新必须与单条 `save_entity` 完全一致：

```sql
INSERT INTO novel_entities (
    book_id, name, aliases, entity_type, description,
    first_appearance_ch, last_appearance_ch, appearance_count,
    importance_score, attributes
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(book_id, name) DO UPDATE SET
    aliases=excluded.aliases,
    entity_type=excluded.entity_type,
    description=excluded.description,
    first_appearance_ch=excluded.first_appearance_ch,
    last_appearance_ch=excluded.last_appearance_ch,
    appearance_count=excluded.appearance_count,
    importance_score=excluded.importance_score,
    attributes=excluded.attributes
```

关系、事件、状态使用各自现有 INSERT SQL 的参数列表，统一在批量方法中调用 `await self._db.commit()`。不调用四个单条方法，避免每个实体触发一次 SQLite 往返。

- [ ] **Step 2: 让 IndexService 使用批量接口并保留兼容降级**

在 `_persist_local_results` 中先完成实体/关系/事件/状态去重，再按族调用 `save_*_batch`。为了兼容已有轻量测试仓储，增加一个内部异步 helper：优先调用批量方法；仓储没有该方法时才逐条调用单条方法。生产 `SqliteNovelRepository` 必须命中批量分支。

实体合并、关系/事件/状态的内存去重逻辑不改变；一次章节的结构化结果仍在同一个索引任务中持久化，单章失败仍由现有外层 `try/except` 隔离。

- [ ] **Step 3: 将向量索引改成“每本书一次健康检查、一次批量 Embedding、一次批量 upsert”**

在 `index_book` 开始阶段调用一次 `vector_store.health()`，保存 `enabled`、`failed` 或 `disabled` 结果。章节提取和持久化成功后，把待向量化的 `(chapter, state)` 收集起来；所有章节本地处理完成后：

1. 调用 `embedding.embed_batch([chapter.raw_text ...])`，复用 EmbeddingAdapter 已有的 `batch_size` 和缓存。
2. 对语义向量创建 `VectorRecord` 列表。
3. 调用一次 `vector_store.upsert(records)`。
4. 按章节更新并保存 `NovelIndexState.vector_status`；无语义 Hash 向量标记 `disabled`，Provider/VectorStore 异常标记 `failed`，但不回滚已完成的本地实体和 BM25。

当 VectorStore 为 disabled 或健康检查失败时，不调用 Embedding Provider。健康检查异常必须和现有测试一致：本地索引仍成功，状态的 `vector_status` 为 `failed`。

- [ ] **Step 4: 添加阶段计时且不把正文写入任务结果**

使用 `time.perf_counter()` 累计 `bm25`、`extract`、`persist`、`vector` 和 `total` 毫秒数，四舍五入到 3 位写入 `IndexResult.timings_ms`。计时只记录时长，不记录章节原文、API Key 或 Prompt 内容；Worker 仅保存这些数字和已有错误信息。

- [ ] **Step 5: 运行 Task 5 测试确认变绿**

Run:

```bash
cd /root/legado-hub/backend
.venv-linux/bin/python -m pytest tests/test_novel_repo.py tests/test_novel_index_service.py tests/test_novel_index_worker.py -q
```

Expected: PASS；向量健康检查为 1 次，Embedding/upsert 为批量调用，批量仓储测试不触发单条方法。

- [ ] **Step 6: 提交分析提速实现**

```bash
cd /root/legado-hub
git add backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py backend/app/services/novel_understanding/index_service.py backend/tests/test_novel_repo.py backend/tests/test_novel_index_service.py backend/tests/test_novel_index_worker.py
git commit -m "perf: batch novel indexing persistence and embeddings"
```

### Task 7: 共享运行时回归和全量验证

**Files:**
- Modify: `backend/tests/test_api_ai.py`

- [ ] **Step 1: 验证 HTTP 依赖只构造一次 Agent/RAG**

在 `test_api_ai.py` 顶部增加 `import pytest`，再增加以下测试。它只替换仓储和 Agent 构造，不触发真实 Provider；当前依赖每次调用都会重新构造，第一组断言应失败。

```python
@pytest.mark.asyncio
async def test_novel_http_dependency_reuses_agent_and_rag(monkeypatch):
    from app.interfaces.http import novel as novel_http

    repository = object()
    built = []
    agent = object()

    async def repository_dependency():
        return repository

    def agent_builder(**kwargs):
        built.append(kwargs)
        return agent

    class Settings:
        def get_novel_settings(self):
            return {"threshold": 0.0}

    monkeypatch.setattr(novel_http, "get_scoped_novel_repository", repository_dependency)
    monkeypatch.setattr(novel_http, "_build_novel_agent_app_service", agent_builder)
    monkeypatch.setattr(novel_http, "build_system_settings_service", lambda: Settings())
    monkeypatch.setattr(novel_http, "build_vector_store", lambda: object())
    novel_http.reset_novel_agent_app_service_cache()

    first = await novel_http.get_novel_agent_app_service()
    second = await novel_http.get_novel_agent_app_service()

    assert first is agent
    assert second is first
    assert len(built) == 1

    novel_http.reset_novel_agent_app_service_cache()
    third = await novel_http.get_novel_agent_app_service()

    assert third is agent
    assert len(built) == 2
```

- [ ] **Step 2: 运行后端完整测试**

Run:

```bash
cd /root/legado-hub/backend
.venv-linux/bin/python -m pytest -q
```

Expected: exit code 0，所有测试通过；若失败，先定位失败所属任务，不修改无关脏文件。

- [ ] **Step 3: 构建前端并确认接口类型没有回归**

Run:

```bash
cd /root/legado-hub/frontend
npm run build
```

Expected: exit code 0；本轮不改 UI，不应出现新的 TypeScript 或 Vite 构建错误。

- [ ] **Step 4: 运行真实书籍 8 的一次索引验收**

在确认正在监听的后端 PID 和数据库路径后，从 `backend` 目录执行：

```bash
cd /root/legado-hub/backend
PYTHONPATH=. .venv-linux/bin/python -c 'import asyncio; from app.tasks.scheduler import run_novel_index_job; print(asyncio.run(run_novel_index_job(limit=10, owner_scope="user:1")))'
```

Expected: 任务结果为 `succeeded`，`processed_chapters >= 1`；随后使用只读查询确认：

```bash
cd /root/legado-hub
python3 - <<'PY'
import sqlite3

novel = sqlite3.connect("backend/data/novel.db")
print(novel.execute(
    "SELECT status, ingest_progress, entity_count, event_count, relationship_count FROM novels WHERE id=8"
).fetchall())
print(novel.execute(
    "SELECT chapter_id, extraction_status FROM novel_index_states WHERE book_id=8"
).fetchall())
novel.close()

main = sqlite3.connect("backend/data/legado_hub.sqlite3")
print(main.execute(
    "SELECT status, result_payload FROM novel_tasks WHERE book_id=8 ORDER BY created_at DESC LIMIT 1"
).fetchall())
main.close()
PY
```

Expected: 书籍为 `ready`、进度为 `1.0`，存在章节索引状态且为 `completed`，任务 payload 中 `processed_chapters` 至少为 1。若 Provider 未配置，向量可以是 `disabled`，不影响本地分析验收。

- [ ] **Step 5: 重启本地 Uvicorn 并做 HTTP 验收**

先用 `ss -ltnp` 找到监听 `127.0.0.1:8000` 的确切 PID，只停止该已确认 PID；从 `backend` 目录以单 Worker 启动：

```bash
cd /root/legado-hub/backend
nohup .venv-linux/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips='*' >/tmp/legado-hub-uvicorn.log 2>&1 &
```

启动后用已有登录 Token 访问 `http://127.0.0.1:8000/api/status`，再通过 Nginx 访问 `http://47.99.116.131:3001/api/status`。

验收内容：

- `/api/ai/conversations` 创建 `book_id=8` 的会话。
- `/api/ai/conversations/{id}/messages` 省略 `book_id` 提问“这本书写得怎么样”。
- 响应中的 `cache_hit`、`citations` 和消息持久化字段存在，Agent 不再反问书名。
- 第二次相同用户、同书、同模型、同问题请求命中用户级缓存且 Provider 调用次数不增加。

- [ ] **Step 6: 提交最终测试变更并记录验证结果**

```bash
cd /root/legado-hub
git status --short
git diff --check
git log --oneline -4
```

使用暂存区文件清单确认只包含本计划最后补充的测试，不把既有无关改动混入。提交消息使用：

```bash
git add backend/tests/test_api_ai.py
git diff --cached --name-only
git commit -m "test: verify shared novel runtime and analysis speed path"
```

## 计划自检

- 规格第 15.1 的三个根因分别由 Tasks 1–2、3–4、5–7 覆盖。
- 规格第 15.2 的绑定 Agent、编号 0、正确状态、批量持久化、缓存/RAG 复用和不盲目并发均有对应任务；没有新建平行小说模型或 Provider 链路。
- 规格第 15.3 的绑定会话、会话继承、编号 0、重复索引、空任务、共享实例和真实书籍 8 验收均有明确测试或命令。
- 所有生产代码步骤都有先失败测试、再实现、再运行测试的顺序。
- 计划未要求删除或覆盖用户已有文件；提交命令按文件精确暂存。
