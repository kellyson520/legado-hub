# Source Agent Joint Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the deterministic source-to-insight acceptance chain as a bounded, auditable `source.joint_test` tool for the `source_build` Agent, while preserving DDD dependency direction and existing knowledge-agent tools.

**Architecture:** Keep orchestration in the application layer. `AgentToolRegistry` owns authorization, a dedicated application executor owns argument validation and result shaping, and `SourceToInsightAcceptanceService` remains a deterministic workflow injected by the infrastructure factory. No application service imports infrastructure implementations, and the acceptance workflow never calls the Agent registry recursively.

**Tech Stack:** Python 3, FastAPI service patterns, dataclasses, pytest/pytest-asyncio, SQLite-backed repositories, existing provider and Legado reading services.

---

## File Structure

- Create `backend/app/application/services/source_joint_test_tool_executor.py`: bounded async tool adapter around the acceptance service.
- Modify `backend/app/application/services/agent_tool_registry.py`: register and allowlist `source.joint_test` for `source_build` only.
- Modify `backend/app/application/services/source_to_insight_acceptance_service.py`: add optional Agent metadata without changing deterministic execution.
- Modify `backend/app/application/services/ai_workspace_service.py`: advertise the tool schema and evidence-first system instruction when granted.
- Modify `backend/app/infrastructure/persistence/factory.py`: compose the acceptance service and joint-test executor with existing application services; inject it into source-build and novel registries without replacing old builders.
- Create `backend/tests/test_source_joint_test_tool_executor.py`: validation, delegation, bounded result, and exception tests.
- Modify `backend/tests/test_agent_tool_registry.py`: built-in presence and source-build-only authorization tests.
- Modify `backend/tests/test_source_to_insight_acceptance_service.py`: optional metadata compatibility test.
- Modify `backend/tests/test_ai_workspace_tool_permissions.py`: schema grant test through the existing workspace permission helper.

Do not modify native Kotlin runtime files or the unrelated dirty runtime changes in this slice.

## Task 1: Registry Contract

**Files:**
- Modify: `backend/app/application/services/agent_tool_registry.py`
- Test: `backend/tests/test_agent_tool_registry.py`

- [ ] **Step 1: Add failing tests**

Append tests asserting that `source.joint_test` exists, is unimplemented by default, is callable only by `source_build`, and accepts an injected async handler:

```python
@pytest.mark.asyncio
async def test_source_joint_test_is_source_build_only_and_handler_is_bounded():
    from app.application.services.agent_tool_registry import AgentToolRegistry
    from app.core.exceptions import AuthorizationException
    from app.domain.entities.agent_runtime import ToolResult

    async def handler(arguments):
        return ToolResult(status="accepted", data={"book_name": arguments["book_name"]})

    registry = AgentToolRegistry(source_build_handlers={"source.joint_test": handler})
    assert registry.get("source.joint_test").category == "operate"
    result = await registry.ainvoke(
        agent_kind="source_build",
        tool_name="source.joint_test",
        arguments={"book_name": "斗罗大陆", "tenant_id": "tenant-1"},
        tenant_id="tenant-1",
    )
    assert result.status == "accepted"
    with pytest.raises(AuthorizationException):
        await registry.ainvoke(
            agent_kind="knowledge",
            tool_name="source.joint_test",
            arguments={"book_name": "斗罗大陆"},
            tenant_id="tenant-1",
        )
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run from `backend`:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_agent_tool_registry.py -k joint_test -q
```

Expected: FAIL because the tool is absent from the built-in and source handler allowlists.

- [ ] **Step 3: Implement the registry entry**

Add `source.joint_test` to the source-build handler allowlist and `_builtin_tools()` with category `operate` and allowed kinds `frozenset({"source_build"})`. Leave the handler unset by default so an unconfigured runtime returns `tool_not_implemented`.

- [ ] **Step 4: Run the registry tests**

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_agent_tool_registry.py -q
```

Expected: all registry tests pass.

## Task 2: Bounded Executor

**Files:**
- Create: `backend/app/application/services/source_joint_test_tool_executor.py`
- Create: `backend/tests/test_source_joint_test_tool_executor.py`

- [ ] **Step 1: Write failing executor tests**

Cover a fake acceptance service and these cases:

```python
@pytest.mark.asyncio
async def test_executor_injects_tenant_and_returns_compact_report():
    from app.application.services.source_joint_test_tool_executor import SourceJointTestToolExecutor

    seen = []

    class Acceptance:
        async def run(self, scenario):
            seen.append(scenario)
            return {"status": "partial", "steps": [{"name": "content", "status": "passed"}], "chapter_candidates": []}

    result = await SourceJointTestToolExecutor(Acceptance()).ainvoke({
        "tenant_id": "tenant-1",
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
        "chapter_index": 0,
    })
    assert result.status == "accepted"
    assert seen[0]["tenant_id"] == "tenant-1"
    assert result.data["report"]["status"] == "partial"
    assert result.data["summary"]["content_passed"] == 1


@pytest.mark.asyncio
async def test_executor_rejects_more_than_four_urls_without_running():
    from app.application.services.source_joint_test_tool_executor import SourceJointTestToolExecutor

    class Acceptance:
        async def run(self, _scenario):
            raise AssertionError("acceptance must not run")

    result = await SourceJointTestToolExecutor(Acceptance()).ainvoke({
        "tenant_id": "tenant-1",
        "source_urls": [f"https://{index}.test" for index in range(5)],
        "book_name": "斗罗大陆",
    })
    assert result.status == "rejected"
    assert result.error_code == "source_urls_limit"
```

Also test missing tenant, invalid URL scheme, negative chapter index, invalid `use_ai`, oversized strings, and conversion of an acceptance exception to `acceptance_failed`.

- [ ] **Step 2: Run the new tests and verify they fail**

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_joint_test_tool_executor.py -q
```

Expected: FAIL because the executor module does not exist.

- [ ] **Step 3: Implement validation and result shaping**

Define `SourceJointTestToolExecutor.ainvoke(arguments) -> ToolResult` with constants `MAX_URLS=4`, `MAX_BOOK_NAME_LENGTH=300`, `MAX_AUTHOR_LENGTH=200`, and `MAX_TITLE_LENGTH=300`. Accept only absolute `http`/`https` URLs, normalize strings, copy `tenant_id` into a new scenario, and call `await acceptance_service.run(scenario)`. Return `{report, summary, agent_joint_test}` under `ToolResult.data`; never return raw exception text containing a traceback.

- [ ] **Step 4: Run executor tests**

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_joint_test_tool_executor.py -q
```

Expected: all executor tests pass.

## Task 3: Acceptance Metadata and Factory Composition

**Files:**
- Modify: `backend/app/application/services/source_to_insight_acceptance_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/tests/test_source_to_insight_acceptance_service.py`

- [ ] **Step 1: Add a compatibility test**

Run the existing acceptance fake flow with `agent_joint_test=True` and assert `report["agent_joint_test"]["enabled"] is True`, while a direct run has no enabled Agent metadata. Keep all existing source/read/complement assertions unchanged.

- [ ] **Step 2: Run the targeted acceptance test and verify it fails**

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py -k agent_joint_test -q
```

Expected: FAIL because the report does not expose Agent metadata.

- [ ] **Step 3: Add optional report metadata**

Read `agent_joint_test` from the scenario and add an `agent_joint_test` report object only when enabled. Its `tool_name` is `source.joint_test`, and `steps` is the ordered list of acceptance step names. Do not call a registry or Agent inside `run()`.

- [ ] **Step 4: Add factory builders**

Add `build_source_to_insight_acceptance_service()` with injected existing application services: `build_source_build_service()`, `build_source_build_runtime_service()`, `build_source_read_service()`, `build_source_complement_service()`, `build_character_calibration_service()`, `build_source_repository()`, and `build_source_runtime_repository()`. Add `build_source_joint_test_tool_executor()` that wraps the acceptance builder. Extend the source-build registry composition with its handler while retaining the current source repair/page handlers. Keep `build_novel_analysis_tool_registry()` behavior unchanged for knowledge tools.

- [ ] **Step 5: Run acceptance and factory import tests**

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py tests/test_source_joint_test_tool_executor.py -q
```

Expected: all tests pass and the factory imports without constructing external providers during module import.

## Task 4: AI Workspace Contract

**Files:**
- Modify: `backend/app/application/services/ai_workspace_service.py`
- Modify: `backend/tests/test_ai_workspace_tool_permissions.py`

- [ ] **Step 1: Add schema/prompt tests**

Assert `_tool_schemas(frozenset({"source.joint_test"}))` contains the six bounded properties and `_system_prompt` requires tool evidence when the tool is granted. Assert an ungranted tool is absent.

- [ ] **Step 2: Run the tests and verify they fail**

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_ai_workspace_tool_permissions.py -q
```

Expected: FAIL because the tool schema and workspace execution branch are absent.

- [ ] **Step 3: Implement the workspace adapter**

Add `source.joint_test` to the tool-name union and schema. Route it through the injected joint-test executor, passing the actor ID as `tenant_id`. Keep it unavailable to the existing knowledge-only `novel_tool_executor` path. Update the prompt to say the Agent must use the tool for source usability and literary claims and must not use parametric memory.

- [ ] **Step 4: Run workspace tests**

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_ai_workspace_tool_permissions.py tests/test_ai_workspace.py -q
```

Expected: all workspace tests pass.

## Task 5: Cross-Layer Verification and Commit

**Files:**
- Modify only files already listed above unless a failing test identifies a direct contract defect.

- [ ] **Step 1: Run focused regression tests**

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest \
  tests/test_agent_tool_registry.py \
  tests/test_source_joint_test_tool_executor.py \
  tests/test_source_to_insight_acceptance_service.py \
  tests/test_ai_workspace_tool_permissions.py \
  tests/test_ai_workspace.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 2: Run static checks**

```bash
/tmp/legado-hub-pytest-venv/bin/python -m compileall -q app
git diff --check
```

Expected: exit code 0 for both commands.

- [ ] **Step 3: Inspect dependency direction**

```bash
rg -n "from app\.infrastructure|import app\.infrastructure" backend/app/application backend/app/domain || true
```

Expected: no new application/domain imports of infrastructure modules; existing violations are recorded before any later architecture slice.

- [ ] **Step 4: Commit only the joint-test slice**

```bash
git add backend/app/application/services/agent_tool_registry.py \
  backend/app/application/services/source_joint_test_tool_executor.py \
  backend/app/application/services/source_to_insight_acceptance_service.py \
  backend/app/application/services/ai_workspace_service.py \
  backend/app/infrastructure/persistence/factory.py \
  backend/tests/test_agent_tool_registry.py \
  backend/tests/test_source_joint_test_tool_executor.py \
  backend/tests/test_source_to_insight_acceptance_service.py \
  backend/tests/test_ai_workspace_tool_permissions.py \
  docs/superpowers/plans/2026-07-18-source-agent-joint-test.md
git commit -m "feat: expose bounded source agent joint test"
```

Do not stage the previous native runtime modifications in this commit.

