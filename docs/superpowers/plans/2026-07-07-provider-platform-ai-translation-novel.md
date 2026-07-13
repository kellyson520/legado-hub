# Provider Platform for AI, Translation, and Novel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shared provider platform that powers real AI, translation, and novel tasks with credential management, model catalogs, retries, fallbacks, quotas, and usage/cost tracking.

**Architecture:** Add shared provider-domain entities and repositories, provider orchestration services, and authenticated API modules that are reused by AI, translation, and novel application services. Keep domain-specific task orchestration separate, but route all provider calls through the same registry, dispatcher, and quota/metering stack.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, SQLite, httpx/OpenAI-compatible SDKs, pytest, React + Vite for console integration

---

> **Git note:** this working copy currently has no `.git`. Replace each “Commit” step with a filesystem checkpoint under `docs/superpowers/reports/checkpoints/`.

## File Structure

```text
backend/app/
├── domain/entities/
│   ├── provider.py                                 # provider account/model/health/usage
│   ├── ai_runtime.py                               # provider-backed ai task/result entities
│   ├── translation_runtime.py                      # chunked translation runtime entities
│   └── novel_runtime.py                            # ingestion/task/result entities
├── domain/repositories/
│   ├── provider_repo.py
│   ├── ai_runtime_repo.py
│   ├── translation_runtime_repo.py
│   └── novel_runtime_repo.py
├── application/services/
│   ├── provider_platform_service.py                # provider registry + health + quotas
│   ├── ai_service.py                               # provider-backed ai tasks
│   ├── translation_service.py                      # chunked provider-backed translation
│   ├── novel_app_service.py                        # ingestion/result access
│   └── novel_agent_service.py                      # provider-backed novel processing
├── infrastructure/providers/
│   ├── base.py
│   ├── registry.py
│   ├── openai_compatible.py
│   └── translators.py
├── infrastructure/persistence/sqlite/
│   ├── schema.py                                   # provider/task/quota tables
│   ├── provider_repo_impl.py
│   ├── ai_runtime_repo_impl.py
│   ├── translation_runtime_repo_impl.py
│   └── novel_runtime_repo_impl.py
├── interfaces/http/
│   ├── ai.py
│   ├── translation.py
│   ├── novel.py
│   └── system.py                                   # providers/quotas/usage
backend/tests/
├── test_provider_platform_repo.py
├── test_provider_platform_service.py
├── test_ai_runtime_service.py
├── test_translation_runtime_service.py
├── test_novel_runtime_service.py
└── test_api_provider_platform.py
frontend/src/
├── api/modules/system.ts
├── api/modules/ai.ts
├── api/modules/translation.ts
└── api/modules/novel.ts
```

### Task 1: Add provider, quota, and usage persistence foundation

**Files:**
- Create: `backend/app/domain/entities/provider.py`
- Create: `backend/app/domain/repositories/provider_repo.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Create: `backend/app/infrastructure/persistence/sqlite/provider_repo_impl.py`
- Test: `backend/tests/test_provider_platform_repo.py`

- [ ] **Step 1: Write the failing test**

```python
from app.infrastructure.persistence.sqlite.provider_repo_impl import SQLiteProviderRepository


def test_create_provider_account_model_and_quota(sqlite_session):
    repo = SQLiteProviderRepository(sqlite_session)
    provider = repo.create_provider_account(name='primary-openai', provider_type='openai_compatible', base_url='https://api.example.com')
    model = repo.create_model(provider.id, name='gpt-4.1-mini', capabilities=['chat', 'json'])
    quota = repo.create_quota_policy(scope_type='user', scope_id='admin', daily_cost_limit=50)
    assert model.provider_account_id == provider.id
    assert quota.scope_id == 'admin'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_provider_platform_repo.py::test_create_provider_account_model_and_quota -v`  
Expected: FAIL because provider repository and schema are missing.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(slots=True)
class ProviderAccount:
    id: str
    name: str
    provider_type: str
    base_url: str
    enabled: bool = True


@dataclass(slots=True)
class QuotaPolicy:
    id: str
    scope_type: str
    scope_id: str
    daily_cost_limit: float
```

```python
class SQLiteProviderRepository(ProviderRepository):
    def create_provider_account(self, name: str, provider_type: str, base_url: str) -> ProviderAccount:
        provider = ProviderAccount(id=uuid4().hex, name=name, provider_type=provider_type, base_url=base_url)
        self.session.add(ProviderAccountModel.from_entity(provider))
        self.session.commit()
        return provider
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_provider_platform_repo.py::test_create_provider_account_model_and_quota -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/domain/entities/provider.py docs/superpowers/reports/checkpoints/2026-07-07-provider-task1.py`  
Expected: checkpoint file exists.

### Task 2: Implement provider registry, health checks, retries, fallbacks, and quota enforcement

**Files:**
- Create: `backend/app/infrastructure/providers/base.py`
- Create: `backend/app/infrastructure/providers/registry.py`
- Create: `backend/app/infrastructure/providers/openai_compatible.py`
- Create: `backend/app/application/services/provider_platform_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Test: `backend/tests/test_provider_platform_service.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_platform_service_retries_then_falls_back_to_secondary_provider(provider_platform_service):
    result = await provider_platform_service.invoke_chat(
        provider_group='default',
        model='gpt-4.1-mini',
        payload={'messages': [{'role': 'user', 'content': 'hello'}]},
        quota_scope=('user', 'admin'),
    )
    assert result.provider_name == 'secondary-openai'
    assert result.attempt_count == 2
```

```python
async def test_platform_service_blocks_requests_after_quota_exhaustion(provider_platform_service):
    with pytest.raises(QuotaExceededError):
        await provider_platform_service.invoke_chat(provider_group='default', model='gpt-4.1-mini', payload={}, quota_scope=('user', 'admin'))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_provider_platform_service.py -v`  
Expected: FAIL because the shared platform service does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
class ProviderPlatformService:
    async def invoke_chat(self, provider_group: str, model: str, payload: dict, quota_scope: tuple[str, str]) -> InvocationResult:
        self.quota_limiter.assert_allowed(quota_scope)
        for account in self.registry.resolve_group(provider_group):
            try:
                return await account.invoke_chat(model=model, payload=payload)
            except ProviderInvocationError as exc:
                last_error = exc
        raise last_error
```

```python
class ProviderRegistry:
    def resolve_group(self, provider_group: str) -> list[ProviderAdapter]:
        return self.providers_by_group[provider_group]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_provider_platform_service.py -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/application/services/provider_platform_service.py docs/superpowers/reports/checkpoints/2026-07-07-provider-task2.py`  
Expected: checkpoint file exists.

### Task 3: Convert AI and translation services to real provider-backed task flows

**Files:**
- Modify: `backend/app/application/services/ai_service.py`
- Modify: `backend/app/application/services/translation_service.py`
- Create: `backend/app/domain/entities/ai_runtime.py`
- Create: `backend/app/domain/entities/translation_runtime.py`
- Create: `backend/app/domain/repositories/ai_runtime_repo.py`
- Create: `backend/app/domain/repositories/translation_runtime_repo.py`
- Create: `backend/app/infrastructure/persistence/sqlite/ai_runtime_repo_impl.py`
- Create: `backend/app/infrastructure/persistence/sqlite/translation_runtime_repo_impl.py`
- Test: `backend/tests/test_ai_runtime_service.py`
- Test: `backend/tests/test_translation_runtime_service.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_ai_service_records_provider_model_usage_and_result(ai_service):
    task = await ai_service.run_character_analysis({'title': 'Demo', 'content': 'Story'}, actor_id='admin')
    assert task['provider'] == 'primary-openai'
    assert task['model'] == 'gpt-4.1-mini'
    assert task['usage']['input_tokens'] > 0
```

```python
async def test_translation_service_splits_large_text_and_retries_failed_chunks(translation_service):
    job = await translation_service.create_job({'text': 'A' * 9000, 'source_language': 'zh', 'target_language': 'en'}, actor_id='admin')
    assert job['chunk_count'] > 1
    assert all(chunk['status'] == 'succeeded' for chunk in job['chunks'])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ai_runtime_service.py backend/tests/test_translation_runtime_service.py -v`  
Expected: FAIL because these services still use placeholder logic.

- [ ] **Step 3: Write minimal implementation**

```python
class AIService:
    async def run_character_analysis(self, payload: dict, actor_id: str) -> dict:
        invocation = await self.platform.invoke_chat(provider_group='ai', model=payload.get('model', 'gpt-4.1-mini'), payload=build_character_prompt(payload), quota_scope=('user', actor_id))
        return self.repo.persist_task_result(kind='character_analysis', actor_id=actor_id, payload=payload, invocation=invocation)
```

```python
class TranslationService:
    async def create_job(self, payload: dict, actor_id: str) -> dict:
        chunks = split_translation_text(payload['text'], max_chars=2000)
        results = [await self._translate_chunk(chunk, actor_id, payload) for chunk in chunks]
        return self.repo.persist_job(actor_id=actor_id, payload=payload, chunks=results)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ai_runtime_service.py backend/tests/test_translation_runtime_service.py -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/application/services/translation_service.py docs/superpowers/reports/checkpoints/2026-07-07-provider-task3.py`  
Expected: checkpoint file exists.

### Task 4: Convert novel ingestion/analysis to shared provider platform

**Files:**
- Modify: `backend/app/application/services/novel_app_service.py`
- Modify: `backend/app/application/services/novel_agent_service.py`
- Create: `backend/app/domain/entities/novel_runtime.py`
- Create: `backend/app/domain/repositories/novel_runtime_repo.py`
- Create: `backend/app/infrastructure/persistence/sqlite/novel_runtime_repo_impl.py`
- Test: `backend/tests/test_novel_runtime_service.py`

- [ ] **Step 1: Write the failing test**

```python
async def test_novel_analysis_pipeline_records_ingestion_task_and_structured_result(novel_agent_service):
    task = await novel_agent_service.start_analysis('novel-1', actor_id='admin')
    assert task['status'] == 'succeeded'
    assert task['provider'] == 'primary-openai'
    assert 'entities' in task['result']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_novel_runtime_service.py -v`  
Expected: FAIL because novel processing is not yet wired into the provider platform.

- [ ] **Step 3: Write minimal implementation**

```python
class NovelAgentService:
    async def start_analysis(self, novel_id: str, actor_id: str) -> dict:
        ingestion = self.repo.get_ingestion(novel_id)
        invocation = await self.platform.invoke_chat(provider_group='novel', model='gpt-4.1-mini', payload=build_novel_analysis_prompt(ingestion), quota_scope=('user', actor_id))
        return self.repo.persist_analysis_result(novel_id=novel_id, actor_id=actor_id, invocation=invocation)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_novel_runtime_service.py -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/application/services/novel_agent_service.py docs/superpowers/reports/checkpoints/2026-07-07-provider-task4.py`  
Expected: checkpoint file exists.

### Task 5: Expose provider/system APIs and connect console modules

**Files:**
- Create: `backend/app/interfaces/http/system.py`
- Modify: `backend/app/interfaces/http/router.py`
- Modify: `backend/app/interfaces/http/ai.py`
- Modify: `backend/app/interfaces/http/translation.py`
- Modify: `backend/app/interfaces/http/novel.py`
- Modify: `frontend/src/api/modules/system.ts`
- Modify: `frontend/src/api/modules/ai.ts`
- Modify: `frontend/src/api/modules/translation.ts`
- Modify: `frontend/src/api/modules/novel.ts`
- Test: `backend/tests/test_api_provider_platform.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_system_provider_api_lists_health_and_quota_state(client, admin_headers):
    response = client.get('/api/system/providers', headers=admin_headers)
    assert response.status_code == 200
    assert response.json()['success'] is True
```

```python
def test_translation_jobs_api_returns_chunk_usage(client, admin_headers):
    response = client.get('/api/translation/jobs', headers=admin_headers)
    assert response.status_code == 200
    assert 'chunks' in response.json()['data'][0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api_provider_platform.py -v`  
Expected: FAIL because the system/provider APIs are incomplete.

- [ ] **Step 3: Write minimal implementation**

```python
@router.get('/providers')
async def list_providers(_=Depends(require_permission(Permission.SYSTEM_SETTINGS_MANAGE))):
    service = build_provider_platform_service()
    data = await service.list_provider_accounts()
    return {'success': True, 'code': 'OK', 'message': 'providers listed', 'data': data, 'meta': {'total': len(data)}, 'trace_id': None}
```

```ts
export async function listProviders() {
  return apiClient.get<ApiEnvelope<ProviderRow[]>>('/api/system/providers')
}
```

- [ ] **Step 4: Run tests and build to verify they pass**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api_provider_platform.py -v; npm --prefix frontend run build`  
Expected: backend tests PASS and frontend build succeeds.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/interfaces/http/system.py docs/superpowers/reports/checkpoints/2026-07-07-provider-task5.py`  
Expected: checkpoint file exists.
