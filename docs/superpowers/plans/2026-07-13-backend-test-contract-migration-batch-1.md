# Backend Test Contract Migration Batch 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复当前后端架构中已复现的 UTF-8 SQL、事件总线 fixture 和 Legado JS harness 回归问题。

**Architecture:** 测试文件负责声明其输入编码；测试共享 fixture 只构造和清理 `MemoryEventBus`；Legado JS profile 作为所有运行阶段的单一白名单，在其中登记 harness 专用阶段。不会恢复旧 routers 或匿名接口。

**Tech Stack:** Python 3.13、pytest、pytest-asyncio、aiosqlite、Legado JS runtime。

---

### Task 1: 让 novel SQL 测试显式使用 UTF-8

**Files:**
- Modify: `backend/tests/test_novel_ingestion_service.py`
- Modify: `backend/tests/test_novel_repo.py`
- Modify: `backend/tests/test_rag_retriever.py`

- [ ] **Step 1: 确认 Windows 默认编码复现失败**

Run:

```powershell
@'
from pathlib import Path
with open(Path("app/database_migrations/novel_schema.sql")) as handle:
    handle.read()
'@ | .\.venv\Scripts\python.exe -
```

Expected: 在 GBK 默认编码环境中以 `UnicodeDecodeError` 失败。

- [ ] **Step 2: 让三个 fixture 明确读取 UTF-8 SQL**

将每个测试 fixture 的：

```python
with open("app/database_migrations/novel_schema.sql") as f:
    await db.executescript(f.read())
```

改为：

```python
with open("app/database_migrations/novel_schema.sql", encoding="utf-8") as f:
    await db.executescript(f.read())
```

- [ ] **Step 3: 运行相关回归**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_novel_ingestion_service.py tests\test_novel_repo.py tests\test_rag_retriever.py
```

Expected: 不再出现 `UnicodeDecodeError`。

### Task 2: 恢复事件总线行为测试的隔离 fixture

**Files:**
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_core_events.py`

- [ ] **Step 1: 使用现有事件总线测试确认 fixture 缺失**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_core_events.py
```

Expected: `fresh_event_bus` 与 `started_event_bus` fixture 不存在。

- [ ] **Step 2: 添加隔离和清理 fixture**

在 `tests/conftest.py` 添加：

```python
import pytest_asyncio

@pytest.fixture
def fresh_event_bus():
    from app.core.events import MemoryEventBus
    return MemoryEventBus()

@pytest_asyncio.fixture
async def started_event_bus():
    from app.core.events import MemoryEventBus
    bus = MemoryEventBus()
    await bus.start()
    try:
        yield bus
    finally:
        await bus.stop()
```

- [ ] **Step 3: 运行事件总线测试**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_core_events.py
```

Expected: 所有测试通过，worker 不遗留后台 task。

### Task 3: 允许规则 harness 运行受控 JS 阶段

**Files:**
- Modify: `backend/app/infrastructure/legado/engine/legado_native_semantics.py`
- Test: `backend/tests/test_engine_selector_pipeline.py`

- [ ] **Step 1: 运行现有 JS harness 回归**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_engine_selector_pipeline.py::test_harness_executes_js_with_timeout_guard
```

Expected: 因 `unsupported js stage: executor_js_rule` 失败。

- [ ] **Step 2: 将 harness 阶段加入兼容 profile 白名单**

在 `LegadoJsCompatProfile.allowed_stages` 中，在规则阶段附近加入：

```python
"executor_js_rule",
```

- [ ] **Step 3: 运行 JS 运行时与 selector 回归**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_engine_selector_pipeline.py tests\test_js_runtime_worker.py tests\test_search_url_js_execution.py
```

Expected: 所有测试通过。

### Task 4: 第一批整体验证与提交

**Files:**
- Modify: `docs/superpowers/specs/2026-07-13-backend-test-contract-migration-design.md`
- Modify: `docs/superpowers/plans/2026-07-13-backend-test-contract-migration-batch-1.md`

- [ ] **Step 1: 运行第一批完整测试**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_novel_ingestion_service.py tests\test_novel_repo.py tests\test_rag_retriever.py tests\test_core_events.py tests\test_engine_selector_pipeline.py tests\test_js_runtime_worker.py tests\test_search_url_js_execution.py
```

Expected: 所有测试通过。

- [ ] **Step 2: 检查差异**

Run:

```powershell
git diff --check
git status --short
```

Expected: 无空白错误，只包含本批文档、测试和兼容配置改动。

- [ ] **Step 3: 提交**

```powershell
git add backend/tests/conftest.py backend/tests/test_novel_ingestion_service.py backend/tests/test_novel_repo.py backend/tests/test_rag_retriever.py backend/app/infrastructure/legado/engine/legado_native_semantics.py docs/superpowers/specs/2026-07-13-backend-test-contract-migration-design.md docs/superpowers/plans/2026-07-13-backend-test-contract-migration-batch-1.md
git commit -m "test: migrate backend regression contracts batch 1"
```
