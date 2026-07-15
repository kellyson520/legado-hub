# Provider Runtime and Source Agent Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the saved OpenAI-compatible provider immediately operable in System Settings and let an explicitly enabled source-build Agent use its bounded tool loop after an unknown site's initial probe fails.

**Architecture:** Keep provider credentials server-side and preserve the existing per-workload route model. The frontend loads provider channels independently from optional route data, so a stale backend never hides the edit and model-discovery controls. The source-build runtime passes explicit operator authorization into policy; the policy continues to block high-risk automation by default, but permits the already sandboxed LLM repair loop only when the source-build Agent is enabled and a `source_build` route exists.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, Python pytest, React, TypeScript, Vitest.

---

### Task 1: Authorize the bounded Agent repair path

**Files:**
- Modify: `backend/app/application/services/agent_policy_service.py`
- Modify: `backend/app/application/services/source_build_agent.py`
- Modify: `backend/app/application/services/source_build_runtime_service.py`
- Test: `backend/tests/test_agent_policy_service.py`
- Test: `backend/tests/test_source_build_runtime_service.py`

- [ ] **Step 1: Write the failing policy test**

```python
def test_policy_allows_high_risk_repair_only_with_explicit_operator_authorization():
    decision = AgentPolicyService().plan_source_repair(
        SiteProfile(site_id='unknown', risk_level='high'),
        evidence={'dom_signature': 'unknown'},
        budget_remaining=600,
        allow_high_risk_llm=True,
    )
    assert decision.strategy == 'llm_repair'
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `/tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_agent_policy_service.py -q`

Expected: the new test fails because `allow_high_risk_llm` is not accepted.

- [ ] **Step 3: Thread explicit authorization through policy and runtime**

```python
# AgentPolicyService.plan_source_repair
if budget_remaining > 0 and (profile.risk_level != 'high' or allow_high_risk_llm):
    return SourceRepairDecision(strategy='llm_repair', ...)

# SourceBuildRuntimeService.handle_job
agent_settings = self._get_agent_settings()
result = self._build_agent.attempt_repair(
    ...,
    allow_high_risk_llm=agent_settings['enabled'] and agent_settings['provider_configured'],
)
```

`SourceBuildAgent.attempt_repair` forwards the keyword argument to policy. The normal high-risk/no-authorization path remains manual review; deterministic success remains model-free.

- [ ] **Step 4: Add a runtime regression test**

Use a high-risk `SiteProfile`, enabled settings, and a recording repair service. Assert the repair service is called once and the persisted `autonomous_build.agent` is not `policy_not_llm_repair`.

- [ ] **Step 5: Run the affected backend tests**

Run: `/tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_agent_policy_service.py backend/tests/test_source_build_agent.py backend/tests/test_source_build_runtime_service.py backend/tests/test_source_build_ai_repair_service.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit the backend authorization change**

```bash
git add backend/app/application/services/agent_policy_service.py backend/app/application/services/source_build_agent.py backend/app/application/services/source_build_runtime_service.py backend/tests/test_agent_policy_service.py backend/tests/test_source_build_runtime_service.py
git commit -m "fix: authorize enabled source build agent repair"
```

### Task 2: Preserve Provider controls when route APIs are unavailable

**Files:**
- Modify: `frontend/src/features/system/ProviderRoutingSettings.tsx`
- Test: `frontend/src/features/system/ProviderRoutingSettings.test.tsx`

- [ ] **Step 1: Write the failing UI regression test**

```tsx
test('keeps saved provider controls available when route loading fails', async () => {
  mocks.getProviderRoute.mockRejectedValueOnce(new Error('route API unavailable'))
  render(<ProviderRoutingSettings onProviderSaved={vi.fn()} />)
  expect(await screen.findByRole('button', { name: 'Get models for Primary' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Edit Primary' })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `node node_modules/vitest/vitest.mjs --run src/features/system/ProviderRoutingSettings.test.tsx`

Expected: the buttons are absent because the current combined `Promise.all` rejects before `setProviders` runs.

- [ ] **Step 3: Split mandatory and optional loading**

```tsx
const providerResponse = await listProviders()
setProviders(providerResponse.data.filter((provider) => !provider.id.startsWith('runtime:')))
const settledRoutes = await Promise.allSettled(ROUTE_GROUPS.map((group) => getProviderRoute(group.id)))
setRoutes(Object.fromEntries(settledRoutes.flatMap((result) => result.status === 'fulfilled' ? [[result.value.data.group, normalizeRouteEntries(result.value.data.entries)]] : [])))
setRouteAvailability(Object.fromEntries(ROUTE_GROUPS.map((group, index) => [group.id, settledRoutes[index].status === 'fulfilled'])))
if (settledRoutes.some((result) => result.status === 'rejected')) setError('Provider routes are temporarily unavailable; channel editing and model discovery remain available.')
```

The Provider list, masked-key display, Edit action, and Models action stay available. Each unavailable route group renders a concise unavailable message and disables its add/reorder controls until the API is present.

- [ ] **Step 4: Run the focused frontend tests**

Run: `node node_modules/vitest/vitest.mjs --run src/features/system/ProviderRoutingSettings.test.tsx src/features/system/SystemSettingsPage.test.tsx`

Expected: all tests pass.

- [ ] **Step 5: Commit the frontend regression fix**

```bash
git add frontend/src/features/system/ProviderRoutingSettings.tsx frontend/src/features/system/ProviderRoutingSettings.test.tsx
git commit -m "fix: keep provider controls available without routes"
```

### Task 3: Activate the repaired runtime and prove its contract

**Files:**
- Modify: `docs/API_MANUAL.md` only if runtime API behavior needs clarification
- Runtime database: `/tmp/legado-hub-ui-20260715.sqlite` (existing data preserved)

- [ ] **Step 1: Restart the local backend process with its existing `DB_PATH` and current source tree**

Start `uvicorn app.main:app --host 0.0.0.0 --port 8000` from `backend/` while preserving `DB_PATH=/tmp/legado-hub-ui-20260715.sqlite` and the existing non-secret runtime options.

- [ ] **Step 2: Confirm the new API contract before using the UI**

Run: query `http://127.0.0.1:8000/openapi.json` and assert it contains `/api/system/provider-routes/{provider_group}` and `/api/system/providers/{provider_id}/models`.

- [ ] **Step 3: Confirm the migration preserves the saved provider**

Read the live SQLite database without printing `api_key`; assert the existing `DeepSeek` channel remains enabled, and `provider_routes` has seeded `source_build` entries.

- [ ] **Step 4: Run full focused verification**

Run backend Provider/routing and source-build tests, then the settings Vitest suite, TypeScript build, and Vite production build. Restore `frontend/tsconfig.tsbuildinfo` after TypeScript build.

- [ ] **Step 5: Commit the plan and any documentation change**

```bash
git add docs/superpowers/plans/2026-07-15-provider-runtime-source-agent-repair.md docs/API_MANUAL.md
git commit -m "docs: plan provider runtime source agent repair"
```
