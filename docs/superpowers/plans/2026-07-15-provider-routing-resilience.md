# Provider Routing and Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Manage multiple OpenAI-compatible providers, discover models, route each AI workload to ordered provider/model pairs, and fail over safely without refreshing the settings page.

**Architecture:** Persist functional route rows separately from provider credentials. The registry resolves ordered provider/model selections per workload; the platform invokes one selection at a time and fails over only on retryable provider errors. The settings page refreshes providers, routes and Agent availability after each save.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy/SQLite, httpx, pytest, React 18, TypeScript, Vitest, Testing Library.

---

## File structure

- `backend/app/domain/entities/provider.py`: `ProviderRoute` entity.
- `backend/app/domain/repositories/provider_repo.py`: editable provider and ordered route contracts.
- `backend/app/infrastructure/persistence/sqlite/{schema.py,bootstrap.py,provider_repo_impl.py}`: route table, legacy backfill and transactions.
- `backend/app/infrastructure/providers/{openai_compatible.py,registry.py}`: model discovery and selections.
- `backend/app/{infrastructure/persistence/factory.py,application/services/provider_platform_service.py,interfaces/http/system.py}`: route construction, failover and API.
- `backend/app/application/services/{ai_service.py,ai_workspace_service.py,source_build_ai_repair_service.py,translation_service.py,novel_agent_service.py}`: select workload routes.
- `frontend/src/api/modules/system.ts`, `frontend/src/features/system/SystemSettingsPage.tsx`: settings API and controls.
- `backend/tests/test_provider_{platform_repo,routing}.py`, `backend/tests/test_api_provider_platform.py`, `frontend/src/features/system/SystemSettingsPage.test.tsx`: coverage.

### Task 1: Persist editable providers and ordered routes

**Files:**
- Modify: `backend/app/domain/entities/provider.py`
- Modify: `backend/app/domain/repositories/provider_repo.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/bootstrap.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/provider_repo_impl.py`
- Test: `backend/tests/test_provider_platform_repo.py`

- [ ] **Step 1: Write a failing repository test.**

```python
def test_provider_repository_preserves_blank_edit_key_and_orders_routes(tmp_path, monkeypatch):
    repo = build_repo(tmp_path, monkeypatch)
    primary = repo.save_provider(name="primary", base_url="https://a.example/v1", api_key="sk-primary", default_model="a-model", enabled=True)
    backup = repo.save_provider(name="backup", base_url="https://b.example/v1", api_key="sk-backup", default_model="b-model", enabled=True)
    edited = repo.save_provider(id=primary.id, name="primary", base_url="https://a2.example/v1", api_key="", default_model="a-model-2", enabled=True)
    routes = repo.replace_routes("source_build", [{"provider_account_id": backup.id, "model": "b-model"}, {"provider_account_id": primary.id, "model": "a-model-2"}])
    assert edited.api_key == "sk-primary"
    assert [(item.provider_account_id, item.priority) for item in routes] == [(backup.id, 0), (primary.id, 1)]
```

- [ ] **Step 2: Run it and verify red.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_provider_platform_repo.py::test_provider_repository_preserves_blank_edit_key_and_orders_routes -q`

Expected: FAIL with `AttributeError` for `save_provider`.

- [ ] **Step 3: Implement the persistence contract.**

```python
@dataclass
class ProviderRoute:
    id: str = ""
    provider_group: str = ""
    provider_account_id: str = ""
    model: str = ""
    priority: int = 0
    enabled: bool = True

class ProviderRouteModel(Base):
    __tablename__ = "provider_routes"
    id = Column(String, primary_key=True)
    provider_group = Column(String, nullable=False, index=True)
    provider_account_id = Column(String, ForeignKey("provider_accounts.id"), nullable=False, index=True)
    model = Column(String, nullable=False)
    priority = Column(Integer, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("provider_group", "priority", name="ux_provider_routes_group_priority"),)
```

Add `save_provider`, `list_routes`, `replace_routes`, `has_routes`, and `list_configured_openai_providers`. `save_provider` must preserve the current key for an empty input; `replace_routes` must replace all group entries in one transaction with contiguous zero-based priorities. Keep `upsert_llm_provider` as a compatibility wrapper.

- [ ] **Step 4: Backfill only missing legacy routes.**

```python
def _ensure_default_provider_routes() -> None:
    repo = SQLiteProviderRepository()
    if repo.has_routes():
        return
    entries = [{"provider_account_id": item.id, "model": item.default_model} for item in repo.list_configured_openai_providers() if item.default_model]
    for group in ("default", "ai", "source_build", "translation", "novel"):
        if entries:
            repo.replace_routes(group, entries)
```

Call it after schema creation and provider column migration; never overwrite a route.

- [ ] **Step 5: Verify green and commit.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_provider_platform_repo.py -q`

Expected: PASS.

Commit: `git add backend/app/domain/entities/provider.py backend/app/domain/repositories/provider_repo.py backend/app/infrastructure/persistence/sqlite/schema.py backend/app/infrastructure/persistence/sqlite/bootstrap.py backend/app/infrastructure/persistence/sqlite/provider_repo_impl.py backend/tests/test_provider_platform_repo.py && git commit -m "feat: persist provider routes"`

### Task 2: Add secure provider, model-discovery and route APIs

**Files:**
- Modify: `backend/app/infrastructure/providers/openai_compatible.py`
- Modify: `backend/app/application/services/provider_platform_service.py`
- Modify: `backend/app/interfaces/http/system.py`
- Test: `backend/tests/test_api_provider_platform.py`

- [ ] **Step 1: Write a failing management API test.**

```python
def test_provider_management_discovers_models_without_leaking_key(client, headers, monkeypatch):
    saved = client.post("/api/system/providers", headers=headers, json={"name": "primary", "base_url": "https://api.example/v1", "api_key": "sk-secret", "default_model": "gpt-a", "enabled": True})
    provider_id = saved.json()["data"]["id"]
    monkeypatch.setattr(OpenAICompatibleProvider, "list_models", AsyncMock(return_value=["gpt-b", "gpt-a"]))
    models = client.post(f"/api/system/providers/{provider_id}/models", headers=headers)
    listed = client.get("/api/system/providers", headers=headers)
    route = client.put("/api/system/provider-routes/ai", headers=headers, json={"entries": [{"provider_account_id": provider_id, "model": "gpt-b"}]})
    assert models.json()["data"] == ["gpt-a", "gpt-b"]
    assert "sk-secret" not in str(listed.json())
    assert route.json()["data"]["entries"][0]["model"] == "gpt-b"
```

- [ ] **Step 2: Run it and verify red.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_api_provider_platform.py::test_provider_management_discovers_models_without_leaking_key -q`

Expected: FAIL with 404 for `POST /api/system/providers`.

- [ ] **Step 3: Implement model discovery and redacted service serialization.**

```python
async def list_models(self) -> list[str]:
    response = await self._client.get(self._models_url(), headers={"Authorization": f"Bearer {self._api_key}"})
    response.raise_for_status()
    return sorted({str(item["id"]) for item in response.json().get("data", []) if item.get("id")})

def _serialize_provider(self, account) -> dict:
    return {"id": account.id, "name": account.name, "base_url": account.base_url, "default_model": account.default_model, "enabled": account.enabled, "api_key_configured": bool(account.api_key), "api_key_masked": self._mask_api_key(account.api_key)}
```

Validate groups `default`, `ai`, `source_build`, `translation`, `novel`, and route providers that are enabled and credentialed. Add provider save/list, route get/replace and discovery service methods. `/llm-settings` must use `save_provider` and ensure legacy default routes.

- [ ] **Step 4: Add permission-protected HTTP routes.**

```python
@router.post("/providers/{provider_id}/models")
async def discover_provider_models(provider_id: str, _=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE))):
    data = await build_provider_platform_service().discover_models(provider_id)
    return {"success": True, "code": "OK", "message": "provider models listed", "data": data, "meta": {}, "trace_id": None}
```

Add `GET`/`POST /providers`, `PUT /providers/{provider_id}`, and `GET`/`PUT /provider-routes/{group}` with Pydantic inputs. No response may include `api_key`.

- [ ] **Step 5: Verify green and commit.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_api_provider_platform.py tests/test_api_system_settings.py -q`

Expected: PASS.

Commit: `git add backend/app/infrastructure/providers/openai_compatible.py backend/app/application/services/provider_platform_service.py backend/app/interfaces/http/system.py backend/tests/test_api_provider_platform.py && git commit -m "feat: manage provider routes and models"`

### Task 3: Apply route-specific models and safe runtime failover

**Files:**
- Modify: `backend/app/infrastructure/providers/registry.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/application/services/provider_platform_service.py`
- Create: `backend/tests/test_provider_routing.py`

- [ ] **Step 1: Write failing runtime tests.**

```python
@pytest.mark.asyncio
async def test_platform_uses_backup_route_model_after_primary_timeout():
    primary = StubProvider("primary", error=httpx.ReadTimeout("timed out"))
    backup = StubProvider("backup", result={"output": {"text": "ok"}})
    platform = ProviderPlatformService(ProviderRegistry({"source_build": [ProviderSelection(primary, "primary-model"), ProviderSelection(backup, "backup-model")]}), AllowAllQuotaLimiter())
    result = await platform.invoke_chat("source_build", None, {"messages": []}, ("user", "1"))
    assert primary.models == ["primary-model"]
    assert backup.models == ["backup-model"]
    assert (result["provider_name"], result["model"]) == ("backup", "backup-model")

@pytest.mark.asyncio
async def test_platform_stops_after_a_422_request_error():
    primary = StubProvider("primary", error=httpx.HTTPStatusError("invalid", request=httpx.Request("POST", "https://a"), response=httpx.Response(422)))
    backup = StubProvider("backup", result={"output": {"text": "unexpected"}})
    platform = ProviderPlatformService(ProviderRegistry({"ai": [ProviderSelection(primary, "a"), ProviderSelection(backup, "b")]}), AllowAllQuotaLimiter())
    with pytest.raises(httpx.HTTPStatusError):
        await platform.invoke_chat("ai", None, {"messages": []}, ("user", "1"))
    assert backup.models == []
```

- [ ] **Step 2: Run them and verify red.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_provider_routing.py -q`

Expected: FAIL with `ImportError` for `ProviderSelection`.

- [ ] **Step 3: Implement selections and retries.**

```python
@dataclass(frozen=True)
class ProviderSelection:
    provider: ProviderAdapter
    model: str

for attempt_count, selection in enumerate(self._registry.resolve_group(provider_group), start=1):
    model = requested_model or selection.model
    try:
        result = await selection.provider.invoke_chat(model=model, payload=payload)
        return self._normalize_result(result, selection.provider, provider_group, model, attempt_count)
    except Exception as exc:
        if self._is_non_retryable_request_error(exc):
            raise
        failures.append(self._sanitize_provider_failure(selection.provider.name, exc))
raise ProviderInvocationError(provider_group, failures)
```

Factory code must join ordered enabled routes to enabled configured accounts. Use an environment provider only if a group has no persisted route. Treat 400/422 as non-retryable; retry timeouts, connection failures, 401/403, 404 model failures, 408/409/425/429 and 5xx. For an explicit unavailable model, retry the next route's configured model. Exhaustion errors must have only sanitized provider failure summaries.

- [ ] **Step 4: Verify green and commit.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_provider_routing.py tests/test_api_provider_platform.py -q`

Expected: PASS.

Commit: `git add backend/app/infrastructure/providers/registry.py backend/app/infrastructure/persistence/factory.py backend/app/application/services/provider_platform_service.py backend/tests/test_provider_routing.py && git commit -m "feat: route provider calls with failover"`

### Task 4: Migrate workloads and implement immediate-refresh settings controls

**Files:**
- Modify: `backend/app/application/services/ai_service.py`
- Modify: `backend/app/application/services/ai_workspace_service.py`
- Modify: `backend/app/application/services/source_build_ai_repair_service.py`
- Modify: `backend/app/application/services/translation_service.py`
- Modify: `backend/app/application/services/novel_agent_service.py`
- Modify: `frontend/src/api/modules/system.ts`
- Modify: `frontend/src/features/system/SystemSettingsPage.tsx`
- Modify: `frontend/src/features/system/SystemSettingsPage.test.tsx`
- Test: `backend/tests/test_provider_routing.py`

- [ ] **Step 1: Write red workload and UI regressions.**

```python
@pytest.mark.asyncio
async def test_source_build_repair_uses_source_build_group():
    class RecordingPlatform:
        groups: list[str] = []
        async def invoke_chat(self, *, provider_group, model, payload, quota_scope):
            self.groups.append(provider_group)
            return {"output": {"message": {"role": "assistant", "content": "", "tool_calls": []}}}
    class PassThroughAIService:
        async def run_source_build_repair(self, payload, actor_id, runner):
            return await runner()
    platform = RecordingPlatform()
    service = SourceBuildAIRepairService(ai_service=PassThroughAIService(), platform=platform, agent_runtime=None)
    await service.repair(tenant_id="tenant-1", run_id="run-1", source_version_id="version-1", url="https://example.test", model="", registry=None)
    assert platform.groups == ["source_build"]
```

```tsx
test('saving a provider immediately refreshes key state and Agent availability', async () => {
  systemMocks.saveProvider.mockResolvedValue(providerEnvelope({ apiKeyConfigured: true, apiKeyMasked: '••••1234' }))
  systemMocks.getSourceBuildAgentSettings.mockResolvedValue(agentEnvelope({ enabled: false, providerConfigured: true }))
  render(<SystemSettingsPage />)
  fireEvent.click(await screen.findByRole('button', { name: 'Save provider' }))
  expect(await screen.findByText('API key: configured (••••1234)')).toBeInTheDocument()
  expect(screen.getByText('LLM provider 已配置 / Provider configured')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run them and verify red.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_provider_routing.py -q && cd ../frontend && npm test -- --run src/features/system/SystemSettingsPage.test.tsx`

Expected: FAIL because source repair uses `ai` and the page lacks Provider controls.

- [ ] **Step 3: Select configured workload defaults.**

```python
invocation = await self._platform.invoke_chat(provider_group="source_build", model=None, payload=payload, quota_scope=("tenant", actor_id))
```

Use route-selected `model=None` for internal AI workspace, translation and novel defaults. Keep a non-empty client payload model as an explicit override and persist `invocation["model"]` in task records.

- [ ] **Step 4: Add the API client, editors and stale-response guard.**

```ts
const refreshVersion = useRef(0)
async function refreshSettings() {
  const requestVersion = ++refreshVersion.current
  const [providerResponse, routeResponses, agentResponse] = await Promise.all([
    listProviderConfigurations(),
    Promise.all(ROUTE_GROUPS.map((group) => getProviderRoute(group.id))),
    getSourceBuildAgentSettings(),
  ])
  if (requestVersion !== refreshVersion.current) return
  setProviders(providerResponse.data)
  setRoutes(routeResponses)
  setSourceBuildAgentSettings(agentResponse.data)
}
```

Export typed provider/route functions. Replace the one-provider form with Provider cards (new/edit, masked key status, fetch-model button, enabled switch) and five functional route editors. Each editor saves a complete ordered entry array, with accessible labelled up/down controls. Call `refreshSettings` at mount and after every save, so an older initial request cannot overwrite newer data.

- [ ] **Step 5: Verify green and commit.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_provider_routing.py tests/test_source_build_ai_repair_service.py tests/test_ai_workspace_service.py tests/test_translation_service.py tests/test_novel_agent_service.py -q && cd ../frontend && npm test -- --run src/features/system/SystemSettingsPage.test.tsx && npm run build`

Expected: all tests PASS and production build exits 0.

Commit: `git add backend/app/application/services/ai_service.py backend/app/application/services/ai_workspace_service.py backend/app/application/services/source_build_ai_repair_service.py backend/app/application/services/translation_service.py backend/app/application/services/novel_agent_service.py frontend/src/api/modules/system.ts frontend/src/features/system/SystemSettingsPage.tsx frontend/src/features/system/SystemSettingsPage.test.tsx backend/tests/test_provider_routing.py && git commit -m "feat: configure provider routes in settings"`

### Task 5: Document and regression-test the finished contract

**Files:**
- Modify: `docs/API_MANUAL.md`
- Test: `backend/tests/test_api_provider_platform.py`
- Test: `backend/tests/test_provider_routing.py`
- Test: `frontend/src/features/system/SystemSettingsPage.test.tsx`

- [ ] **Step 1: Add exact API contract documentation.**

```markdown
| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/system/providers` | List redacted Provider configurations |
| `POST` | `/api/system/providers/{id}/models` | Discover models without returning a stored key |
| `GET` / `PUT` | `/api/system/provider-routes/{group}` | Read or atomically replace a functional route |
```

- [ ] **Step 2: Run backend regression.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_provider_platform_repo.py tests/test_api_provider_platform.py tests/test_api_system_settings.py tests/test_provider_routing.py tests/test_source_build_ai_repair_service.py tests/test_ai_workspace_service.py tests/test_translation_service.py tests/test_novel_agent_service.py -q`

Expected: PASS.

- [ ] **Step 3: Run frontend regression and production build.**

Run: `cd frontend && npm test -- --run src/features/system/SystemSettingsPage.test.tsx src/features/operations/AgentRunsPage.test.tsx && npm run build`

Expected: PASS and build exits 0.

- [ ] **Step 4: Check secret safety and commit.**

Run: `git diff --check && rg -n 'api_key.*return|"api_key"\s*:' backend/app frontend/src/api docs/API_MANUAL.md`

Expected: no whitespace errors and no raw credential in a settings response.

Commit: `git add docs/API_MANUAL.md backend/tests/test_api_provider_platform.py backend/tests/test_provider_routing.py frontend/src/features/system/SystemSettingsPage.test.tsx && git commit -m "docs: document provider routing controls"`
