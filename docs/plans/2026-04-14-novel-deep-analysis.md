# Novel Deep Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 让一份 TXT 小说通过导入、代码索引、人物/时间/事件分析和预算受控的可选深析形成可验证闭环，并用本地书源 fixture 验证搜索与下载。

**Architecture:** 先把章节文本转为内容 hash 缓存的确定性代码报告，再从报告选择少量证据进入现有 evidence-first analysis task；LLM 只处理代码无法消解的低置信度歧义。书源验收使用本地 aiohttp fixture 调用现有 BookSearcher/ingestion flow，不依赖公网。

**Tech Stack:** Python 3.11, dataclasses, FastAPI, pytest, pytest-asyncio, aiohttp fixture, existing SQLite repositories, existing NovelAnalysisTaskService.

**Spec:** `docs/design/2026-04-14-novel-deep-analysis.md`

## Global Constraints

- 无 LLM provider 时，代码分析必须可独立完成。
- 所有候选必须包含 chapter_id、start/end offset 或明确章节证据。
- 代码分析结果按内容 SHA-256 缓存；相同内容重跑不得产生新分析调用。
- 每个深析任务继承 max_tokens_per_task、max_tool_calls_per_task、max_chapters_per_task 上限。
- 不把整本小说正文发送给 LLM；只发送候选相关章节窗口。
- 低置信度人物别名、关系和未锚定相对时间不得自动发布。
- 不新增外部运行时依赖；使用现有 Python/FastAPI/aiohttp/pytest。

---

### Task 1: Deterministic Analysis Models and Extractors

**Files:**
- Create: `backend/app/domain/entities/novel_code_analysis.py`
- Create: `backend/app/application/services/novel_code_analysis_service.py`
- Create: `backend/tests/test_novel_code_analysis.py`

**Interfaces:**
- Produces `NovelCodeAnalysisService.analyze(work_id: str, chapters: list[dict]) -> NovelCodeAnalysisReport`.
- Each chapter input dict contains `chapter_id`, `chapter_index`, `title`, `content`.
- Report contains `content_sha256`, `chapters`, `characters`, `cooccurrences`, `time_mentions`, `events`, `warnings`, and `cache_hit`.

- [x] **Step 1: Write failing tests**

```python
def test_code_analysis_extracts_characters_time_mentions_and_evidence():
    report = NovelCodeAnalysisService().analyze("work-1", [{
        "chapter_id": "c1", "chapter_index": 1, "title": "雨夜",
        "content": "林默在子时抵达长安。苏晚看见林默，三天后他们在城门重逢。"
    }])
    assert "林默" in [item.name for item in report.characters]
    assert any(item.normalized == "子时" for item in report.time_mentions)
    assert any(item.normalized == "三天后" and item.anchor_status == "unresolved" for item in report.time_mentions)
    assert report.characters[0].evidence[0].chapter_id == "c1"
    assert report.cooccurrences[0].count >= 1
```

- [x] **Step 2: Run RED**

Run: `cd backend && python3 -m pytest tests/test_novel_code_analysis.py -q`
Expected: FAIL because the report models/service do not exist.

- [x] **Step 3: Implement minimal deterministic extraction**

Implement dataclasses for `EvidenceLocation`, `CharacterCandidate`, `TimeMention`, `EventCandidate`, `Cooccurrence`, and `NovelCodeAnalysisReport`. Use Unicode-aware regex and chapter-local offsets. Extract Chinese name candidates from repeated 2–4 character names near narrative verbs, time lexicon (`年/月/日/时/刻/天后/之前/之后/当晚/翌日`), and event triggers (`发现/进入/离开/决定/战斗/死亡/重逢`). Keep alias merging as candidates with confidence; do not auto-merge uncertain names.

- [x] **Step 4: Run GREEN**

Run: `cd backend && python3 -m pytest tests/test_novel_code_analysis.py -q`
Expected: PASS.

- [x] **Step 5: Add cache behavior test and implementation**

```python
def test_same_content_hash_returns_cached_report_without_reextracting():
    service = NovelCodeAnalysisService()
    chapters = [{"chapter_id": "c1", "chapter_index": 1, "title": "一", "content": "林默进入长安。"}]
    first = service.analyze("work-1", chapters)
    second = service.analyze("work-1", chapters)
    assert first.content_sha256 == second.content_sha256
    assert second.cache_hit is True
```

Run the test, then add an in-memory cache keyed by `(work_id, content_sha256)` and rerun the full file.

- [x] **Step 6: Commit**

```bash
git add backend/app/domain/entities/novel_code_analysis.py backend/app/application/services/novel_code_analysis_service.py backend/tests/test_novel_code_analysis.py
git commit -m "feat: add deterministic novel code analysis"
```

### Task 2: Evidence Selection and Budget Contract

**Files:**
- Modify: `backend/app/application/services/novel_analysis_task_service.py`
- Modify: `backend/app/application/services/novel_analysis_pipeline_service.py`
- Create: `backend/tests/test_novel_deep_analysis_contract.py`

**Interfaces:**
- Produces `select_analysis_evidence(report, *, max_chapters: int, max_spans: int) -> list[dict]`.
- Produces `NovelAnalysisTaskService.normalize_policy(policy) -> dict` with hard bounded token/tool/chapter values.

- [x] **Step 1: Write failing budget tests**

```python
def test_analysis_policy_clamps_tokens_tools_and_chapters():
    policy = NovelAnalysisTaskService.normalize_policy({
        "max_tokens_per_task": 999999,
        "max_tool_calls_per_task": 0,
        "max_chapters_per_task": 999,
    })
    assert policy == {"max_tokens_per_task": 200000, "max_tool_calls_per_task": 1, "max_chapters_per_task": 50}

def test_evidence_selection_never_selects_more_than_budgeted_chapters():
    selected = select_analysis_evidence(report, max_chapters=2, max_spans=4)
    assert len({item["chapter_id"] for item in selected}) <= 2
    assert len(selected) <= 4
```

- [x] **Step 2: Run RED**

Run: `cd backend && python3 -m pytest tests/test_novel_deep_analysis_contract.py -q`
Expected: FAIL because normalization helper/evidence selector are absent.

- [x] **Step 3: Implement minimal helpers**

Move policy clamping into a public static method used by `create_task`. Rank evidence by explicit time/character/event candidates, then chapter order, deduplicate by `(chapter_id,start_offset,end_offset)`, and enforce both limits before returning excerpts.

- [x] **Step 4: Run GREEN and regression**

Run: `cd backend && python3 -m pytest tests/test_novel_deep_analysis_contract.py backend/tests/test_novel_upload_contract.py -q`
Expected: PASS.

- [x] **Step 5: Verify pipeline never sends unbounded evidence**

Add a fake platform test that records payload lengths and asserts `_invoke_role` receives only selected evidence and raises `RuntimeError("analysis task token budget exhausted")` before another call when the budget is exhausted.

- [x] **Step 6: Commit**

```bash
git add backend/app/application/services/novel_analysis_task_service.py backend/app/application/services/novel_analysis_pipeline_service.py backend/tests/test_novel_deep_analysis_contract.py
git commit -m "feat: enforce bounded novel analysis evidence"
```

### Task 3: Local Source Search and Download Fixture Flow

**Files:**
- Create: `backend/tests/test_novel_source_fixture_flow.py`
- Modify: `backend/app/services/book_searcher.py` only if the test exposes a real parsing defect.
- Modify: `backend/app/application/services/novel_ingestion_service.py` only if the existing source flow cannot consume fixture detail/toc/chapter responses.

**Interfaces:**
- Test fixture exposes JSON search, detail, TOC, and chapter endpoints using `aiohttp.web.Application`.
- Test invokes existing source/search/ingestion services and asserts returned book, chapters, content variants, and evidence span IDs.

- [x] **Step 1: Write failing integration fixture test**

Create a local server with `/search`, `/book/1`, `/book/1/toc`, `/book/1/chapter/1`, `/book/1/chapter/2`. Configure a `BookSource` whose `searchUrl` and `ruleSearch` use JSONPath. Assert search returns the fixture book and ingestion downloads two chapters.

- [x] **Step 2: Run RED**

Run: `cd backend && python3 -m pytest tests/test_novel_source_fixture_flow.py -q`
Expected: FAIL only if the real source flow cannot parse or persist fixture responses; capture the first concrete failure.

- [x] **Step 3: Implement the smallest parser/flow fix**

Do not rewrite the source engine. Preserve existing URL safety, source ownership, evidence creation, and content hash behavior. Add a regression assertion for each fixed response shape.

- [x] **Step 4: Run GREEN**

Run: `cd backend && python3 -m pytest tests/test_novel_source_fixture_flow.py backend/tests/test_source_build_agent_workflow.py -q`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add backend/tests/test_novel_source_fixture_flow.py backend/app/services/book_searcher.py backend/app/application/services/novel_ingestion_service.py
git commit -m "test: cover source search and novel download fixture flow"
```

### Task 4: Analysis Report HTTP Contract

**Files:**
- Modify: `backend/app/interfaces/http/novel_analysis.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Create: `backend/tests/test_novel_analysis_report_contract.py`

**Interfaces:**
- Adds `GET /api/novel-analysis/works/{work_id}/code-report?chapter_limit=...`.
- Response data contains `content_sha256`, `cache_hit`, `characters`, `cooccurrences`, `time_mentions`, `events`, `warnings`.
- No LLM provider is required for this endpoint.

- [x] **Step 1: Write failing route test**

Use the existing test app/auth fixtures and monkeypatch repository/service builders. Assert a work with two chapters returns a report and that the second request returns `cache_hit: true`.

- [x] **Step 2: Run RED**

Run: `cd backend && python3 -m pytest tests/test_novel_analysis_report_contract.py -q`
Expected: FAIL because the route/builder is absent.

- [x] **Step 3: Implement route and builder**

Build the canonical content repository, load at most `chapter_limit` chapters, invoke `NovelCodeAnalysisService`, serialize dataclasses recursively, and return the existing `ok` envelope. Reject `chapter_limit > 50` through FastAPI validation.

- [x] **Step 4: Run GREEN**

Run: `cd backend && python3 -m pytest tests/test_novel_analysis_report_contract.py backend/tests/test_novel_deep_analysis_contract.py -q`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/interfaces/http/novel_analysis.py backend/app/infrastructure/persistence/factory.py backend/tests/test_novel_analysis_report_contract.py
git commit -m "feat: expose deterministic novel analysis report"
```

### Task 5: End-to-End Acceptance and Release Validation

**Files:**
- Modify: `docs/design/2026-04-14-novel-deep-analysis.md` if actual contracts require clarification.
- Modify: `README.md` with a reproducible TXT → report → optional deep-analysis walkthrough.
- Create: `backend/tests/test_novel_end_to_end_acceptance.py` if the prior fixtures can be composed without network.

- [x] **Step 1: Add acceptance test**

Use a small deterministic Chinese TXT fixture, run parser/import or equivalent canonical builders, run code report, select evidence, and create a bounded analysis task with no platform. Assert the report is complete and the task remains auditable rather than claiming an LLM result.

- [x] **Step 2: Run RED and GREEN**

Run the focused acceptance test before implementation changes, then after the minimal wiring. Expected final result: PASS with no external network and no LLM key.

- [x] **Step 3: Run complete verification**

```bash
cd backend && python3 -m pytest -q
cd ../frontend && npm ci --ignore-scripts --no-audit --no-fund && npm run test -- --run && npm run build
cd .. && docker compose config
```

Expected: all backend/frontend tests pass, frontend build succeeds, default Compose renders.

- [x] **Step 4: Review and commit**

```bash
git diff --check
git status --short
git add -A
git commit -m "feat: add code-first novel deep analysis pipeline"
```
