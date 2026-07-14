# Source-Build Agent Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an administrator-controlled source-build Agent that uses bounded page tools only after deterministic building fails and submits successful rules for review.

**Architecture:** A persisted system switch defaults off. An enabled source-build runtime passes same-origin page tools and a live full-chain validator to the existing OpenAI-compatible tool loop. Successful Agent patches are candidate-only and create review items; no tool can publish or enable a source.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy SQLite, aiohttp, OpenAI-compatible function calling, React, TypeScript, pytest, Vitest.

---

## File Structure

- Create `backend/app/domain/entities/system_setting.py`, `backend/app/domain/repositories/system_settings_repo.py`, and `backend/app/infrastructure/persistence/sqlite/system_settings_repo_impl.py` for persistent booleans.
- Modify `backend/app/infrastructure/persistence/sqlite/schema.py`, `backend/app/infrastructure/persistence/factory.py`, and `backend/app/interfaces/http/system.py` for the setting table, composition, and API.
- Create `backend/app/application/services/system_settings_service.py` and `backend/tests/test_api_system_settings.py` for source-build Agent setting behavior.
- Create `backend/app/application/services/source_page_tool_executor.py` and `backend/tests/test_source_page_tool_executor.py` for bounded public-web tools.
- Modify `backend/app/application/services/agent_tool_registry.py`, `source_build_tool_executor.py`, `source_build_ai_repair_service.py`, `ai_service.py`, and `source_build_runtime_service.py` for an async Agent loop and candidate review result.
- Modify `backend/tests/test_agent_tool_registry.py`, `test_source_build_ai_repair_service.py`, `test_ai_runtime_service.py`, `test_source_build_runtime_service.py`, and `test_api_source_build.py` for integration coverage.
- Modify `frontend/src/api/modules/system.ts`, `frontend/src/features/system/SystemSettingsPage.tsx`, and `frontend/src/features/system/SystemSettingsPage.test.tsx` for the administrator switch.

### Task 1: Persist and expose the Agent switch

**Files:**
- Create: `backend/app/domain/entities/system_setting.py`
- Create: `backend/app/domain/repositories/system_settings_repo.py`
- Create: `backend/app/infrastructure/persistence/sqlite/system_settings_repo_impl.py`
- Create: `backend/app/application/services/system_settings_service.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/interfaces/http/system.py`
- Test: `backend/tests/test_api_system_settings.py`

- [ ] **Step 1: Write the failing API test.**

```python
def test_source_build_agent_setting_defaults_disabled_and_persists(monkeypatch, tmp_path):
    client, headers = build_admin_client(monkeypatch, tmp_path)
    assert client.get('/api/system/source-build-agent-settings', headers=headers).json()['data']['enabled'] is False
    assert client.put('/api/system/source-build-agent-settings', headers=headers, json={'enabled': True}).json()['data']['enabled'] is True
    assert client.get('/api/system/source-build-agent-settings', headers=headers).json()['data']['enabled'] is True
```

- [ ] **Step 2: Run the test and confirm RED.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_api_system_settings.py -q`

Expected: FAIL because the endpoint does not exist.

- [ ] **Step 3: Implement boolean persistence and authorized endpoints.**

```python
SOURCE_BUILD_AGENT_ENABLED = 'source_build_agent_enabled'

def get_source_build_agent_settings(self) -> dict:
    return {'enabled': self._repo.get_bool(SOURCE_BUILD_AGENT_ENABLED, default=False),
            'provider_configured': self._provider_available()}

def set_source_build_agent_enabled(self, enabled: bool) -> dict:
    self._repo.set_bool(SOURCE_BUILD_AGENT_ENABLED, enabled)
    return self.get_source_build_agent_settings()
```

Define `SystemSettingModel(key, value, updated_at)` with a unique key. `get_bool` accepts stored `true`/`false`; `set_bool` upserts in one transaction. Add GET/PUT endpoints protected by `system.settings.manage` and inject the service from the factory.

- [ ] **Step 4: Verify GREEN and commit.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_api_system_settings.py tests/test_api_provider_platform.py -q`

Expected: PASS.

Commit: `git add backend/app/domain/entities/system_setting.py backend/app/domain/repositories/system_settings_repo.py backend/app/infrastructure/persistence/sqlite/system_settings_repo_impl.py backend/app/application/services/system_settings_service.py backend/app/infrastructure/persistence/sqlite/schema.py backend/app/infrastructure/persistence/factory.py backend/app/interfaces/http/system.py backend/tests/test_api_system_settings.py && git commit -m "feat: add source build agent system setting"`

### Task 2: Implement same-origin page tools and async tool calls

**Files:**
- Create: `backend/app/application/services/source_page_tool_executor.py`
- Modify: `backend/app/application/services/agent_tool_registry.py`
- Modify: `backend/app/application/services/source_build_tool_executor.py`
- Test: `backend/tests/test_source_page_tool_executor.py`
- Test: `backend/tests/test_agent_tool_registry.py`

- [ ] **Step 1: Write the failing page-boundary tests.**

```python
@pytest.mark.asyncio
async def test_page_tools_allow_target_origin_and_redact_sensitive_data():
    result = await SourcePageToolExecutor('https://books.example/list', FakeHttp()).inspect({'url': '/search'})
    assert result.status == 'accepted'
    assert result.data['url'] == 'https://books.example/search'
    assert 'cookie=' not in result.data['excerpt'].lower()

@pytest.mark.asyncio
async def test_page_tools_reject_cross_origin_and_sensitive_headers():
    tools = SourcePageToolExecutor('https://books.example/list', FakeHttp())
    assert (await tools.request({'url': 'https://other.example/', 'method': 'GET'})).error_code == 'cross_origin_url'
    assert (await tools.request({'url': '/search', 'method': 'POST', 'headers': {'Authorization': 'x'}})).error_code == 'unsafe_headers'
```

- [ ] **Step 2: Run the tests and confirm RED.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_page_tool_executor.py tests/test_agent_tool_registry.py -q`

Expected: FAIL because page tools and `ainvoke` do not exist.

- [ ] **Step 3: Implement bounded tools.**

`page.inspect` accepts only a same-origin URL and sends GET. `page.request` accepts only same-origin GET/POST, a form dictionary no larger than 4 KiB, and rejects all header parameters. Both return only `url`, `status`, `response_kind`, discovered forms, bounded link/DOM summaries, and a 4 KiB sanitized excerpt. Redact cookie/authorization patterns before truncation and close the HTTP client through `aclose`.

- [ ] **Step 4: Add awaited registry support.**

```python
async def ainvoke(self, *, agent_kind, tool_name, arguments, tenant_id):
    tool = self._authorize(agent_kind, tool_name, arguments, tenant_id)
    result = tool.handler(arguments)
    return await result if inspect.isawaitable(result) else result
```

Keep `invoke` for synchronous users and return `async_tool_requires_ainvoke` for awaitable handlers. Add only `page.inspect` and `page.request` to the fixed source-build allowlist. Make `rule.validate` await a validator when its callback returns an awaitable; require full validation before `review.request` succeeds.

- [ ] **Step 5: Verify GREEN and commit.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_page_tool_executor.py tests/test_agent_tool_registry.py tests/test_source_build_tool_executor.py -q`

Expected: PASS.

Commit: `git add backend/app/application/services/source_page_tool_executor.py backend/app/application/services/agent_tool_registry.py backend/app/application/services/source_build_tool_executor.py backend/tests/test_source_page_tool_executor.py backend/tests/test_agent_tool_registry.py backend/tests/test_source_build_tool_executor.py && git commit -m "feat: add bounded source page agent tools"`

### Task 3: Upgrade the repair prompt and observe-act-verify loop

**Files:**
- Modify: `backend/app/application/services/source_build_ai_repair_service.py`
- Modify: `backend/app/application/services/ai_service.py`
- Test: `backend/tests/test_source_build_ai_repair_service.py`
- Test: `backend/tests/test_ai_runtime_service.py`

- [ ] **Step 1: Write a failing scripted-provider loop test.**

```python
@pytest.mark.asyncio
async def test_repair_loop_inspects_proposes_validates_and_requests_review():
    result = await repair_service.repair(..., registry=scripted_registry)
    assert result['repair']['state'] == 'validated_for_review'
    assert result['repair']['patch'] == {'searchUrl': 'https://books.test/search?q={{key}}'}
    assert result['repair']['prompt_version'] == 'source-build-agent/v1'
```

- [ ] **Step 2: Run the test and confirm RED.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_build_ai_repair_service.py -q`

Expected: FAIL because the loop has generic schemas and calls `registry.invoke` synchronously.

- [ ] **Step 3: Implement concrete schemas and prompt.**

Set `PROMPT_VERSION = 'source-build-agent/v1'`. Require evidence-first inspection, standard Legado patch fields, successful `rule.validate`, candidate-only review, and no prose final result. Define each function schema with `additionalProperties: false`; `page.request` has only `url`, `method`, and `form`.

- [ ] **Step 4: Await calls and retain outcome.**

Use `await registry.ainvoke`, record each tool result, stop at review acceptance or four model turns, and return `repair` with `state`, `patch`, `validation`, `review`, `prompt_version`, and tool count. Update `AIService.run_source_build_repair` so the persisted task result includes this `repair` object.

- [ ] **Step 5: Verify GREEN and commit.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_build_ai_repair_service.py tests/test_ai_runtime_service.py -q`

Expected: PASS.

Commit: `git add backend/app/application/services/source_build_ai_repair_service.py backend/app/application/services/ai_service.py backend/tests/test_source_build_ai_repair_service.py backend/tests/test_ai_runtime_service.py && git commit -m "feat: add verified source build agent loop"`

### Task 4: Gate the runtime and persist review-only candidates

**Files:**
- Modify: `backend/app/application/services/source_build_runtime_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Test: `backend/tests/test_source_build_runtime_service.py`
- Test: `backend/tests/test_api_source_build.py`

- [ ] **Step 1: Write RED tests for disabled, deterministic-success, Agent-success, and no-provider cases.**

```python
def test_runtime_does_not_call_agent_when_switch_off_or_probe_valid(...):
    assert fake_repair.calls == []

def test_runtime_agent_full_validation_creates_candidate_review_without_publish(...):
    result = service.handle_job(job)
    assert result['decision'] == 'review'
    assert updated.payload['autonomous_build']['agent']['state'] == 'validated_for_review'
    assert updated.payload['source_rule']['searchUrl'] == 'https://books.test/search?q={{key}}'

def test_runtime_records_skipped_not_configured(...):
    assert updated.payload['autonomous_build']['agent']['state'] == 'skipped_not_configured'
```

- [ ] **Step 2: Run the tests and confirm RED.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_build_runtime_service.py tests/test_api_source_build.py -q`

Expected: FAIL because runtime has no persisted setting gate or Agent validation callback.

- [ ] **Step 3: Implement deterministic-first runtime dependencies.**

Inject `agent_settings` and `page_tool_factory`. Only create page tools when policy selects `llm_repair`, `enabled` is true, and `provider_configured` is true. The async validation callback must merge only `ALLOWED_PATCH_FIELDS`, probe the merged rule through a new client session, and return the normal search/TOC/content validation report. Close page and probe clients in `finally`.

- [ ] **Step 4: Convert validated repair to review-only state.**

On `validated_for_review`, persist the merged candidate rule, `autonomous_build.agent`, and a review item; return `decision='review'`, `strategy='agent_tool_loop'`, and `review_required=True`. For provider failure, rejected tools, or budget exhaustion, persist the structured Agent outcome and retain escalation behavior. Do not call any publish or enable method.

- [ ] **Step 5: Verify GREEN and commit.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_build_runtime_service.py tests/test_api_source_build.py tests/test_source_build_agent.py -q`

Expected: PASS.

Commit: `git add backend/app/application/services/source_build_runtime_service.py backend/app/infrastructure/persistence/factory.py backend/tests/test_source_build_runtime_service.py backend/tests/test_api_source_build.py && git commit -m "feat: gate source build agent and review candidates"`

### Task 5: Add the System Settings UI switch

**Files:**
- Modify: `frontend/src/api/modules/system.ts`
- Modify: `frontend/src/features/system/SystemSettingsPage.tsx`
- Test: `frontend/src/features/system/SystemSettingsPage.test.tsx`

- [ ] **Step 1: Write the failing component test.**

```tsx
expect(await screen.findByRole('switch', { name: 'Agent-enhanced source build' })).not.toBeChecked()
fireEvent.click(screen.getByRole('switch', { name: 'Agent-enhanced source build' }))
await waitFor(() => expect(systemMocks.updateSourceBuildAgentSettings).toHaveBeenCalledWith({ enabled: true }))
```

- [ ] **Step 2: Run the test and confirm RED.**

Run: `cd frontend && npm test -- SystemSettingsPage.test.tsx --run`

Expected: FAIL because the setting client and switch do not exist.

- [ ] **Step 3: Implement typed client and accessible switch.**

```ts
export interface SourceBuildAgentSettings { enabled: boolean; providerConfigured: boolean; provider_configured?: boolean }
export const getSourceBuildAgentSettings = () => apiClient.get<SourceBuildAgentSettings>('/system/source-build-agent-settings')
export const updateSourceBuildAgentSettings = (payload: { enabled: boolean }) => apiClient.put<SourceBuildAgentSettings>('/system/source-build-agent-settings', payload)
```

Load it with provider settings. The `role="switch"` control explains that Agent calls occur only after deterministic failure, shows missing-provider status, and disables while saving.

- [ ] **Step 4: Verify GREEN and commit.**

Run: `cd frontend && npm test -- SystemSettingsPage.test.tsx --run`

Expected: PASS.

Commit: `git add frontend/src/api/modules/system.ts frontend/src/features/system/SystemSettingsPage.tsx frontend/src/features/system/SystemSettingsPage.test.tsx && git commit -m "feat: add source build agent settings switch"`

### Task 6: Verify the complete path

**Files:**
- Verify only: all files in Tasks 1–5 and `backend/scripts/smoke_source_to_insight.py`.

- [ ] **Step 1: Run the focused backend suite.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_api_system_settings.py tests/test_source_page_tool_executor.py tests/test_agent_tool_registry.py tests/test_source_build_ai_repair_service.py tests/test_source_build_runtime_service.py tests/test_api_source_build.py tests/test_source_probe_service.py -q`

Expected: PASS without unclosed client warnings.

- [ ] **Step 2: Run the settings UI test.**

Run: `cd frontend && npm test -- SystemSettingsPage.test.tsx --run`

Expected: PASS.

- [ ] **Step 3: Run an Agent-off smoke.**

Run: `cd backend && DB_PATH=/tmp/source-agent-off.sqlite /tmp/legado-hub-pytest-venv/bin/python scripts/smoke_source_to_insight.py --source-url https://www.biquga.com/list/0/1.html --output /tmp/source-agent-off.json`

Expected: deterministic source build succeeds and report records no Agent invocation.

- [ ] **Step 4: Run an Agent-on mock-provider smoke after credentials are supplied.**

Run: `cd backend && DB_PATH=/tmp/source-agent-on.sqlite /tmp/legado-hub-pytest-venv/bin/python scripts/smoke_source_to_insight.py --source-url <operator-target> --use-ai --output /tmp/source-agent-on.json`

Expected: report has bounded, sanitized tool calls and an Agent candidate review; no source is published.

- [ ] **Step 5: Request review and check scoped changes.**

Run: `git diff --check && git status --short`

Expected: no scoped whitespace errors and no unrelated files staged.
