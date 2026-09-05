# Agent TXT Source Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有 LegadoHub 架构的前提下，完善 TXT/文本预览与分章、Agent 工具交互、Agent 写源状态机，并为每个行为提供可运行测试。

**Architecture:** 复用现有 `NovelDocumentParser`、`NovelIngestionService`、`AgentToolRegistry` 和 `SourceBuildAgent`。新增 preview/quality 层只负责纯解析与结构化结果；接口层保持薄；Agent 工具只读或产生候选，正式发布仍由审核流水线负责。

**Tech Stack:** Python 3.11+、FastAPI、Pydantic、pytest/pytest-asyncio、现有 SQLite repository；不新增模型供应商或前端状态库。

**Spec:** `docs/design/2026-08-04-agent-txt-source-workbench.md`

## Global Constraints

- 所有新增后端业务代码必须位于 `backend/app/domain`、`backend/app/application`、`backend/app/infrastructure` 或 `backend/app/interfaces/http` 的正确边界内。
- 不得绕过 `AgentToolRegistry` 的 agent kind、tenant scope 和 evidence 约束。
- 兼容 `POST /api/novel/books/import/upload` 现有字段：`book_id`、`duplicate`、`status`、`task_id`、`error_code`。
- Preview 不写入书籍、章节、原始文件或分析任务。
- 不得自动发布未经 `rule.validate` 和人工审核的书源。
- 每个新行为必须先写失败测试并亲眼确认失败，再写最小实现。

---

### Task 1: Text preview and quality contract

**Files:**
- Modify: `backend/app/application/services/novel_ingestion/parsers.py`
- Create: `backend/app/application/services/novel_ingestion/quality.py`
- Test: `backend/tests/test_novel_text_preview.py`

**Interfaces:**
- Consumes: `NovelDocumentParser.parse(filename, media_type, data)` and `ParsedNovelDocument`.
- Produces: `NovelImportWarning(code: str, message: str, chapter_index: int | None = None)`, `NovelImportPreview(content_hash: str, title: str, author: str, media_type: str, total_chars: int, chapters: list[dict], warnings: list[NovelImportWarning])`, and `build_import_preview(document, *, max_chapters=5000, min_chapter_chars=20)`.

- [ ] **Step 1: Write failing tests**

Add tests asserting:

```python
from app.application.services.novel_ingestion.quality import build_import_preview
from app.application.services.novel_ingestion.parsers import NovelDocumentParser

def test_preview_reports_no_heading_and_chapter_summary():
    document = NovelDocumentParser().parse("book.txt", "text/plain", "正文第一段\n正文第二段".encode())
    preview = build_import_preview(document)
    assert len(preview.chapters) == 1
    assert any(item.code == "no_heading_detected" for item in preview.warnings)
    assert preview.chapters[0]["word_count"] > 0

def test_preview_reports_empty_or_tiny_chapters_without_rejecting_document():
    document = NovelDocumentParser().parse("book.txt", "text/plain", "第一章\n短\n第二章\n这是足够长的章节内容".encode())
    preview = build_import_preview(document, min_chapter_chars=5)
    assert any(item.code == "short_chapter" for item in preview.warnings)
```

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest tests/test_novel_text_preview.py -q`
Expected: collection/import failure because `quality.py` and `build_import_preview` do not exist.

- [ ] **Step 3: Implement the minimal quality module**

Create immutable dataclasses. Derive each chapter summary from `ParsedChapter` with `ordinal`, `title`, `word_count`, `content_hash`, and a bounded `preview` of the first 120 characters. Emit `no_heading_detected` when the document has one chapter whose title equals the filename stem or “正文”; emit `short_chapter` for chapters below `min_chapter_chars`; emit `too_many_chapters` when the count exceeds `max_chapters`. Do not mutate the parsed document.

- [ ] **Step 4: Run GREEN**

Run: `cd backend && python -m pytest tests/test_novel_text_preview.py -q`
Expected: all focused tests pass.

- [ ] **Step 5: Refactor and commit**

Run: `cd backend && python -m pytest tests/test_novel_text_preview.py -q && python -m compileall -q app tests`
Then commit: `git add backend/app/application/services/novel_ingestion backend/tests/test_novel_text_preview.py && git commit -m "feat: add text import preview quality contract"`

---

### Task 2: Preview-aware ingestion service and HTTP endpoint

**Files:**
- Modify: `backend/app/application/services/novel_ingestion_service.py`
- Modify: `backend/app/interfaces/http/novel.py`
- Test: `backend/tests/test_novel_upload_preview.py`
- Test: `backend/tests/test_api_novel.py`

**Interfaces:**
- Consumes: `NovelDocumentParser`, `build_import_preview`, existing `NovelIngestionService.import_upload`.
- Produces: `NovelIngestionService.preview_upload(owner_scope, filename, media_type, data, *, title="", author="") -> NovelImportPreview`; `POST /api/novel/books/import/preview`; existing upload response extended with `preview` and `warnings` while retaining old keys.

- [ ] **Step 1: Write failing service tests**

Add a fake repository test that calls `preview_upload` and asserts the repository has no save calls and the returned preview contains chapter summaries. Add a route contract test asserting the preview endpoint exists and rejects an empty upload with HTTP 400 and `empty_document`.

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest tests/test_novel_upload_preview.py tests/test_api_novel.py -q`
Expected: failure because `preview_upload` and `/books/import/preview` do not exist.

- [ ] **Step 3: Implement minimal service and route**

In `NovelIngestionService`, parse bytes and call `build_import_preview`; do not access repository or runtime repo. In `novel.py`, add a `preview_upload` route with the same permission dependency as upload, read the file once, translate `NovelImportError` to HTTP 400 with its `code`, and serialize dataclasses to JSON. In the existing upload route, create one preview before `import_upload` and include its serialized summary in `data`; preserve `book_id`, `duplicate`, `status`, `task_id`, and `error_code`.

- [ ] **Step 4: Run GREEN**

Run: `cd backend && python -m pytest tests/test_novel_upload_preview.py tests/test_api_novel.py -q`
Expected: focused API/service tests pass.

- [ ] **Step 5: Run regression and commit**

Run: `cd backend && python -m pytest tests/test_novel_import_service.py tests/test_api_novel.py -q` (use the existing matching test filename if the repository names differ), then commit the service and route changes.

---

### Task 3: Agent-facing import quality tools

**Files:**
- Modify: `backend/app/application/services/agent_tool_registry.py`
- Modify: `backend/app/application/services/novel_agent_app_service.py` only where tool metadata is exposed
- Test: `backend/tests/test_agent_import_tools.py`

**Interfaces:**
- Consumes: `AgentToolRegistry`, `NovelImportPreview`, existing tenant enforcement.
- Produces: registered tools `novel.import_preview`, `novel.chapter_quality`, `source.build_status`, `source.validation_report`; handlers accept a dict and return `ToolResult`; each tool remains read-only and requires the correct agent kind and tenant scope.

- [ ] **Step 1: Write failing registry tests**

Assert that `novel.import_preview` and `novel.chapter_quality` are present for `novel`/`knowledge`, `source.build_status` and `source.validation_report` are present for `source_build`, and an argument containing another `tenant_id` raises `AuthorizationException`. Assert an unbound handler returns `tool_not_implemented` rather than executing arbitrary input.

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest tests/test_agent_import_tools.py -q`
Expected: failures because the four tool names are not registered.

- [ ] **Step 3: Implement minimal registrations and metadata**

Add the four read tools to `_builtin_tools` with explicit allowed agent kinds. Keep handlers unset until composition provides them. Extend any app-service tool listing metadata without duplicating the registry’s authorization logic. Do not add direct database/network access to the registry.

- [ ] **Step 4: Run GREEN**

Run: `cd backend && python -m pytest tests/test_agent_import_tools.py tests/test_agent_tool_registry.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

Commit with `feat: expose audited import and source diagnostic tools`.

---

### Task 4: Source-build agent state machine

**Files:**
- Modify: `backend/app/application/services/source_build_agent.py`
- Test: `backend/tests/test_source_build_agent_workflow.py`

**Interfaces:**
- Consumes: existing `AgentPolicyService.plan_source_repair`, `SourceReviewService.enqueue_build_escalation`.
- Produces: `SourceBuildStep(status: str, name: str, passed: bool, details: dict)`, extended `SourceBuildAgentResult` with `attempt_id`, `status`, `steps`, and `reason_tags`; `SourceBuildAgent.run_workflow(...) -> SourceBuildAgentResult`.

- [ ] **Step 1: Write failing workflow tests**

Test deterministic repair with both validations passing returns `status == "canary"`, ordered steps `planned`, `proposed`, `validating`, `canary`, and no review item. Test failed validation returns `status == "escalated"` and a review item. Test LLM strategy with positive budget returns `status == "deferred"`, never `canary`.

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest tests/test_source_build_agent_workflow.py -q`
Expected: failure because `run_workflow` and step metadata do not exist.

- [ ] **Step 3: Implement minimal state machine**

Use `uuid4().hex` for `attempt_id`. Reuse `plan_source_repair`; append deterministic step records. A candidate canary is allowed only when deterministic strategy and both fixture/sample validations pass. LLM strategy becomes deferred. All other paths enqueue review using the existing service and return escalated. Keep `attempt_repair` backward-compatible by delegating or preserving its existing result fields.

- [ ] **Step 4: Run GREEN and regression**

Run: `cd backend && python -m pytest tests/test_source_build_agent_workflow.py tests/test_source_build_agent.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

Commit with `feat: add auditable source build workflow states`.

---

### Task 5: Frontend upload preview and Agent timeline

**Files:**
- Modify: `frontend/src/api/modules/novel.ts`
- Modify: `frontend/src/features/novel/NovelLibraryPage.tsx`
- Modify: `frontend/src/features/novel/NovelReaderPage.tsx` or the existing Agent workspace page identified by route search
- Test: matching frontend module/page tests

**Interfaces:**
- Consumes: `POST /api/novel/books/import/preview` and existing `/books/import/upload` envelopes.
- Produces: preview-before-submit upload flow showing warnings/chapter count; Agent message rendering of tool steps, evidence/citations, and review-required state.

- [ ] **Step 1: Write failing React tests**

Test upload preview renders a warning and chapter count before submit; test Agent tool result renders tool name, status, and citation/evidence label.

- [ ] **Step 2: Run RED**

Run: `cd frontend && npm run test -- --run <focused test files>`
Expected: failures because preview state and tool timeline rendering are absent.

- [ ] **Step 3: Implement minimal UI**

Use existing API client and UI primitives. Do not create a second HTTP client. Preview must be dismissible; submit uses the already previewed file and preserves compatibility with the existing upload action. Render unknown tool result fields safely as JSON/markdown using existing sanitization components.

- [ ] **Step 4: Run GREEN**

Run focused Vitest tests, then `npm run test -- --run`.

- [ ] **Step 5: Build and commit**

Run `npm run build`, then commit the frontend changes.

---

### Task 6: Full verification and review

**Files:**
- Modify: documentation only if commands or API behavior changed.
- Test: full backend/frontend suites.

- [ ] **Step 1: Run backend verification**

Run `cd backend && python -m pytest -q && python -m compileall -q app tests`.

- [ ] **Step 2: Run frontend verification**

Run `cd frontend && npm run test -- --run && npm run build`.

- [ ] **Step 3: Review diff and architecture**

Run `git diff --check`, inspect changed files, and run the dependency-direction test. Fix any critical/major findings before completion.

- [ ] **Step 4: Record outcome**

Update the design/README with actual verification results and list any network/dependency blockers without claiming unrun checks passed.
