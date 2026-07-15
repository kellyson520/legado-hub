# Agent Tool Wire Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let OpenAI-compatible models call source-build and AI-workspace tools through provider-valid function names while keeping every call mapped back to the existing bounded, read-only server tool policy.

**Architecture:** Source-build tools retain their dotted internal names and registry permissions, but expose underscore-only wire aliases to models and canonicalize aliases before dispatch. The AI workspace publishes schemas for its three existing read-only tools, executes a bounded model tool loop, appends sanitized tool results to the model context, and returns the same tool-history format the UI already renders.

**Tech Stack:** Python, FastAPI service layer, OpenAI-compatible function calls, pytest, React, Vitest.

---

### Task 1: Use provider-valid source-build tool aliases

**Files:**
- Modify: `backend/app/application/services/source_build_ai_repair_service.py`
- Test: `backend/tests/test_source_build_ai_repair_service.py`

- [ ] **Step 1: Write the failing alias test**

```python
schemas = SourceBuildAIRepairService._tool_schemas()
assert {item['function']['name'] for item in schemas} == {
    'source_inspect', 'page_inspect', 'page_request', 'source_probe',
    'rule_propose', 'rule_validate', 'review_request',
}
```

Add a scripted model response using `rule_validate` and assert the agent runtime records the canonical `rule.validate` tool.

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `/tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_source_build_ai_repair_service.py -q`

Expected: the existing dotted wire tool schemas fail the assertion and no alias is resolved.

- [ ] **Step 3: Add one-way wire-to-canonical mapping**

```python
_WIRE_TOOL_NAMES = {
    'source.inspect': 'source_inspect',
    'page.inspect': 'page_inspect',
    'page.request': 'page_request',
    'source.probe': 'source_probe',
    'rule.propose': 'rule_propose',
    'rule.validate': 'rule_validate',
    'review.request': 'review_request',
}
```

Generate schemas from aliases and translate every model-returned function name back to the canonical registry name before logging, executing, collecting validation evidence, or deciding review completion. Reject unknown aliases without invoking a tool.

- [ ] **Step 4: Run source-build repair tests**

Run: `/tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_source_build_ai_repair_service.py backend/tests/test_source_build_runtime_service.py -q`

Expected: all tests pass and recorded names remain canonical dotted names.

### Task 2: Give the AI workspace a bounded autonomous read-only tool loop

**Files:**
- Modify: `backend/app/application/services/ai_workspace_service.py`
- Test: `backend/tests/test_ai_workspace_service.py`
- Test: `frontend/src/features/ai/AIWorkspacePage.test.tsx`

- [ ] **Step 1: Write the failing model-tool-loop test**

```python
platform = ScriptedWorkspacePlatform([
    tool_response('list_visible_sources', {}),
    text_response('已读取可见书源。'),
])
reply = await service.send_message(conversation['id'], '7', 'chat', '列出书源')
assert reply['content'] == '已读取可见书源。'
assert reply['tool_calls'][0]['name'] == 'list_visible_sources'
assert platform.calls[0]['payload']['tools'][0]['function']['name'] == 'list_visible_sources'
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `/tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_ai_workspace_service.py -q`

Expected: the current workspace payload has no `tools` and returns the first scripted tool response as plain assistant content.

- [ ] **Step 3: Implement the bounded loop without widening authority**

```python
for _turn in range(3):
    invocation = await self._platform.invoke_chat(
        provider_group='ai', model=None,
        payload={'messages': messages, 'tools': self._tool_schemas(), 'tool_choice': 'auto'},
        quota_scope=('user', str(actor_id)),
    )
    calls = self._model_tool_calls(invocation)
    if not calls:
        return final_text, tool_calls
    tool_calls.extend(await self._execute_model_tool_calls(actor_id, calls))
    messages.extend(tool_response_messages)
```

Only `list_visible_sources`, `get_source_rule_summary`, and `list_ai_analysis_results` are exposed. Validate arguments with the existing Pydantic models, sanitize results before persistence and prompting, reject unknown calls, cap turns at three, and preserve the existing optional user-selected read-only tools.

- [ ] **Step 4: Run workspace backend and UI tests**

Run: `/tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_ai_workspace_service.py backend/tests/test_ai_runtime_service.py -q`

Run: `node node_modules/vitest/vitest.mjs --run src/features/ai/AIWorkspacePage.test.tsx`

Expected: all tests pass; the existing UI renders model-selected tool history without new permission controls.

### Task 3: Validate the real provider contract and source-build repair

**Files:**
- Runtime database: `/tmp/legado-hub-ui-20260715.sqlite` (existing provider and candidates preserved)

- [ ] **Step 1: Verify provider-valid names against the saved DeepSeek channel**

Send one minimal `max_tokens=1` function-call request using source-build schemas and assert the provider no longer returns the function-name validation error.

- [ ] **Step 2: Submit one fresh candidate for `https://m.bqgiu.cc/` with keyword `剑来`**

Inspect the resulting Agent run and assert that model tool invocations are recorded after the deterministic content probe detects the access wall. Do not publish the candidate unless full search, TOC, and content validation succeeds.

- [ ] **Step 3: Run focused Provider, source-build, and workspace verification**

Run the Provider/routing, source-build, AI workspace, and UI test suites; run TypeScript and Vite production build; restore `frontend/tsconfig.tsbuildinfo` after the build.

- [ ] **Step 4: Commit and merge the repair**

```bash
git add backend/app/application/services/source_build_ai_repair_service.py backend/app/application/services/ai_workspace_service.py backend/tests/test_source_build_ai_repair_service.py backend/tests/test_ai_workspace_service.py docs/superpowers/plans/2026-07-15-agent-tool-wire-compatibility.md
git commit -m "fix: support provider-compatible agent tool calls"
```
