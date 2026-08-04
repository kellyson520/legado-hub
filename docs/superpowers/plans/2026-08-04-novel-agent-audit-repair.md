# Novel Agent Audit Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the concrete production defects identified by `/上传/novel-agent-audit-checklist.md`, preserve the already-merged OpenHarness work, and leave the repository testable on the supported local Python runtime before pushing `main`.

**Architecture:** Keep `NovelAgentAppService` as the owner-scoped application boundary and reuse the existing ProviderPlatform, repository, cache, vector-store, and AgentRuntime abstractions. The legacy `services/novel_agent` runtime remains a compatibility surface, but its configuration, permissions, tool execution, memory persistence, and provider orchestration must fail explicitly and share the same safety rules. Retrieval and indexing remain local-first with optional semantic providers and typed degradation.

**Tech Stack:** Python 3.10+, FastAPI, pytest/pytest-asyncio, aiosqlite, SQLAlchemy, SQLite/WAL, existing OpenAI-compatible/Anthropic/Gemini adapters, React/Vite frontend.

---

## Audit Baseline

The uploaded checklist contains 84 findings, but its branch snapshot predates the current `main`. The following items are verified as already implemented and are regression-only in this plan: centralized HTTP routing and dependency direction, owner-scoped novel routes, `/api/ai` novel-agent injection, zero-based chapter selection, evidence-first index snapshots, ProviderPlatform adapter routing, vector record owner/version boundaries, and OpenHarness v1 protocol/adapters. The implementation work below targets current, reproducible gaps rather than restoring obsolete duplicate routes.

### Task 1: Make the supported local runtime importable

**Files:**
- Modify: `backend/app/core/logging.py`
- Modify: `backend/app/domain/entities/interactive_browser.py`
- Test: `backend/tests/test_runtime_compatibility.py`

- [x] **Step 1: Write failing compatibility tests**

```python
def test_logging_uses_a_writable_default_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("LOG_DIR", raising=False)
    assert resolve_log_dir(tmp_path).is_relative_to(tmp_path)

def test_interactive_browser_state_is_a_string_enum_on_python_310():
    from app.domain.entities.interactive_browser import InteractiveBrowserState
    assert str(InteractiveBrowserState.PENDING) == "pending"
```

- [x] **Step 2: Run `pytest -q tests/test_runtime_compatibility.py` and verify the import/default-path failures are reproduced.**
- [x] **Step 3: Implement a project/runtime fallback for `LOG_DIR` and a Python 3.10-compatible `StrEnum` fallback without changing production container behavior when `LOG_DIR` is explicitly configured.**
- [x] **Step 4: Run the compatibility tests and the import-heavy novel/vector test files.**

### Task 2: Close application tool safety gaps

**Files:**
- Modify: `backend/app/application/services/novel_agent_app_service.py`
- Modify: `backend/app/services/novel_agent/registry.py`
- Modify: `backend/app/services/novel_agent/config.py`
- Modify: `backend/app/services/novel_agent/mcp.py`
- Test: `backend/tests/test_novel_agent_app_service.py`
- Test: `backend/tests/test_novel_agent_runtime_safety.py`

- [x] **Step 1: Add failing tests for required tool arguments, JSON-schema type/range validation, denied/ask/allow permission decisions, malformed model tool arguments, and MCP error responses.**
- [x] **Step 2: Run only those tests and confirm each fails for the missing validation/permission behavior.**
- [x] **Step 3: Add a single schema validator for the existing tool definitions; validate before execution and return typed `ValidationException`/authorization outcomes. Make `list_tools` honor owner scope, book scope, enabled categories, and indexed-book capabilities.**
- [x] **Step 4: Add configured permission evaluation to the legacy registry/MCP path, normalize malformed arguments into tool errors, and replace silent config loading failures with explicit typed errors/logging.**
- [x] **Step 5: Run the new tests plus existing agent/security/MCP tests.**

### Task 3: Make application assembly reusable and safe

**Files:**
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/application/services/novel_agent_app_service.py`
- Modify: `backend/app/application/services/novel_cache_service.py`
- Test: `backend/tests/test_novel_agent_app_service.py`
- Test: `backend/tests/test_novel_cache_service.py`
- Test: `backend/tests/test_factory_lifecycle.py`

- [x] **Step 1: Add failing tests proving scoped builders reuse the retriever/cache/service, concurrent `get_or_set` evaluates a factory once, and answer keys are independent of conversation id while retaining owner/book/knowledge isolation.**
- [x] **Step 2: Run the focused tests and record the duplicate-build/cache-stampede failures.**
- [x] **Step 3: Add lock-protected cache fill, bounded/replaceable book-key tracking, and remove conversation identity from knowledge-answer cache keys.**
- [x] **Step 4: Cache scoped retrievers and the application service behind lifecycle locks; inject the same novel service into AI workspace construction and expose an async close/reset hook for tests and shutdown.**
- [x] **Step 5: Run factory, cache, workspace, security, and novel-agent application tests.**

### Task 4: Repair streaming, loop limits, and explicit fallback

**Files:**
- Modify: `backend/app/application/services/novel_agent_app_service.py`
- Modify: `backend/app/interfaces/http/novel.py`
- Modify: `backend/app/application/services/novel_model_selection_service.py`
- Test: `backend/tests/test_novel_agent_app_service.py`
- Test: `backend/tests/test_api_novel_agent.py`

- [x] **Step 1: Add failing tests for stream cache hit/miss behavior, completed assistant persistence on a stream, configurable tool-loop limits, and local-evidence fallback when the Provider is unavailable.**
- [x] **Step 2: Run those tests and confirm the current one-shot stream/no-cache and hard-coded `range(3)` behavior.**
- [x] **Step 3: Route streaming through the same cache key and write successful final results; emit structured started/delta/citation/usage/completed/error events while preserving the existing compatibility response shape.**
- [x] **Step 4: Read loop limits from novel settings, validate model selection against configured route availability, and return a bounded evidence-only response when the Provider path is unavailable instead of exposing internal exceptions.**
- [x] **Step 5: Run application and HTTP regression tests.**

### Task 5: Improve retrieval and indexing correctness

**Files:**
- Modify: `backend/app/application/services/novel_understanding/retriever.py`
- Modify: `backend/app/application/services/novel_understanding/embedding.py`
- Modify: `backend/app/application/services/novel_understanding/index_service.py`
- Modify: `backend/app/application/services/system_settings_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Test: `backend/tests/test_novel_understanding.py`
- Test: `backend/tests/test_novel_index_service.py`
- Test: `backend/tests/test_novel_retrieval_quality.py`

- [x] **Step 1: Add failing tests for min-max/RRF-compatible score fusion, query token matching for KG relations, local semantic fallback policy, batch embedding context, empty-book status, zero-number chapters, and stage timing output.**
- [x] **Step 2: Run the focused tests and verify the current mixed-unit score and empty-book success failures.**
- [x] **Step 3: Normalize each retrieval track before weighting, use token-aware matching for entities/events/relations, and let the configured embedding adapter participate when a semantic provider is available without confusing hash vectors for semantic evidence.**
- [x] **Step 4: Reuse one vector health check and one batch embedding/upsert per book, preserve chapter `canonical_num=0`, add `status`, `no_chapters`, and `timings_ms` to `IndexResult`, and use a production-safe default local vector backend when the settings store is uninitialized.**
- [x] **Step 5: Run index, retrieval, vector-store, and settings tests.**

### Task 6: Provider quota, retry, and configuration reliability

**Files:**
- Modify: `backend/app/application/services/provider_platform_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/services/novel_agent/config.py`
- Modify: `backend/app/infrastructure/providers/openai_compatible.py`
- Test: `backend/tests/test_provider_platform_service.py`
- Test: `backend/tests/test_provider_resilience.py`
- Test: `backend/tests/test_novel_agent_core.py`

- [x] **Step 1: Add failing tests for quota policy enforcement, retry count/backoff classification, all-provider error aggregation without secret leakage, stream error preservation, and invalid TOML/JSON configuration errors.**
- [x] **Step 2: Run the tests and verify the allow-all limiter, provider iteration-only retry, and silent exception paths.**
- [x] **Step 3: Implement a repository-backed quota limiter using the existing quota policy/usage abstractions, bounded exponential backoff with jitter and timeout-aware retry classification, and typed sanitized provider errors.**
- [x] **Step 4: Make the shared provider adapter surface preserve error types in streaming and make legacy Agent provider initialization report configuration failures explicitly.**
- [x] **Step 5: Run provider, API, OpenHarness, and legacy Agent tests.**

### Task 7: Legacy Agent runtime and skills must be honest and useful

**Files:**
- Modify: `backend/app/services/novel_agent/reasonix_agent.py`
- Modify: `backend/app/services/novel_agent/agent.py`
- Modify: `backend/app/services/novel_agent/memory.py`
- Modify: `backend/app/services/novel_agent/store.py`
- Modify: `backend/app/services/novel_agent/skills/extractor.py`
- Modify: `backend/app/services/novel_agent/skills/grapher.py`
- Modify: `backend/app/services/novel_agent/skills/ocr.py`
- Modify: `backend/app/services/novel_agent/skills/writer.py`
- Modify: `backend/app/services/novel_agent/skills/reasoner.py`
- Test: `backend/tests/test_novel_agent_core.py`
- Test: `backend/tests/test_novel_agent_skills.py`
- Test: `backend/tests/test_novel_agent_memory.py`

- [x] **Step 1: Add failing tests for planner-provider invocation, concurrent independent tool calls, explicit reflection/fallback metadata, session-scoped persisted history, deduplicated extractor patterns, safe graph HTML embedding, OCR output formats, and provider-backed writer/reasoner behavior.**
- [x] **Step 2: Run the focused tests and confirm the current unused planner, passive memory, regex, XSS, and fixed-template failures.**
- [x] **Step 3: Implement the smallest behavior that satisfies those contracts: planner output feeds executor, independent tool calls use bounded concurrency, reflection runs after tool observations, memory stores a session id and reloads history, and skills call an injected provider when configured while returning explicit unavailable results otherwise.**
- [x] **Step 4: Add SQLite FTS5-backed lookup where supported and keep bounded in-memory indexes for compatibility; never swallow malformed files/configuration.**
- [x] **Step 5: Run all legacy Agent/skill tests and the full backend suite.**

### Task 8: Verify, document, commit, and push

**Files:**
- Modify: `docs/ARCHITECTURE_CURRENT.md`
- Modify: `docs/superpowers/plans/2026-08-04-novel-agent-audit-repair.md`
- Test: all backend/frontend test and build commands

- [x] **Step 1: Update the current architecture/audit status with verified behavior and explicit optional-provider limitations; do not edit `/上传/novel-agent-audit-checklist.md`.**
- [x] **Step 2: Run Python compilation, focused audit tests, the complete backend suite, frontend tests, frontend build, OpenHarness schema validation, and `git diff --check`.**
- [x] **Step 3: Review the diff for secrets, untracked files, user logs, generated artifacts, and scope regressions.**
- [ ] **Step 4: Commit the repair in focused commits, re-run the final verification after the last commit, and push the resulting commits to `origin/main` only after confirming the remote branch and local HEAD.**

## Verification Commands

```bash
cd backend
pytest -q
python3 -m compileall -q app tests
cd ../frontend
npm test -- --run
npm run build
cd ..
git diff --check
```

## Review Notes

- Do not delete `/上传/novel-agent-audit-checklist.md`.
- Do not delete or stage the user-owned `backend/logs/` directory.
- Do not replace the existing OpenHarness implementation with the private DeepSeek protocol; retain the model-neutral adapter boundary.
- Do not claim an external vector/LLM feature is available when its provider is absent; return a typed, observable degradation path.
