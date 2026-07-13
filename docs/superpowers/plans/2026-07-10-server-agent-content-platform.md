# 服务端 Agent 内容平台 Implementation Plan

## Sync Status (2026-07-13)

- **Rule engine / source writing UI:** Added the Engine console `Rule writing studio` to `frontend/src/features/engine/EngineRunsPage.tsx`. Operators can submit a `Source URL` plus optional `Keyword`, queue a console `source.build` job, see `Queued job <job_id>`, and refresh candidate source versions without leaving the diagnostics page.
- **Candidate visibility:** Engine console now lists live source-build candidates with source URL, candidate status, source rule name (`bookSourceName` fallback), autonomous decision/strategy, `validation <grade> / <quality_score>`, and search/toc/content probe status plus sample title or failure reason. The original engine run timeline and `deployment decision` card remain on the page.
- **Console API contract:** `frontend/src/api/modules/engine.ts` now exposes `listEngineSourceBuilds()` and `submitEngineSourceBuild({ url, keyword })`, targeting `GET /api/engine/source-builds` and `POST /api/engine/source-builds`. Backend console endpoints are protected by `engine.test`/`engine.generate` and submit jobs with `trigger: console_rule_lab`.
- **Verification:**
  - `npm test -- --run src/features/engine/EngineRunsPage.test.tsx` -> `1 passed file, 3 passed tests`.
  - `npm test -- --run src/app/providers/ThemeProvider.test.tsx src/components/layout/AppConsoleShell.test.tsx src/features/sources/SourceListPage.test.tsx src/features/sources/SourceHealthPage.test.tsx src/features/sources/SourceHealthDetailPage.test.tsx src/features/engine/EngineRunsPage.test.tsx src/features/system/SystemSettingsPage.test.tsx src/features/auth/LoginPage.test.tsx src/app/router/guards.test.tsx src/features/operations/AgentRunsPage.test.tsx src/features/operations/JobsPage.test.tsx src/features/operations/EventDeliveriesPage.test.tsx src/features/operations/SourceBuildsPage.test.tsx src/features/operations/ReviewQueuePage.test.tsx` -> `14 passed files, 26 passed tests`.
  - `npm run build` -> `built`.
  - `backend/.venv/Scripts/python.exe -m pytest tests/test_api_engine_runtime.py tests/test_source_build_runtime_service.py tests/test_api_source_build.py -q` -> `15 passed`.
  - `backend/.venv/Scripts/python.exe -m pytest tests/test_event_delivery_service.py tests/test_event_delivery_scheduler.py tests/test_event_delivery_lifespan.py tests/test_runtime_bootstrap.py tests/test_api_health.py tests/test_work_knowledge_service.py tests/test_api_work_knowledge.py tests/test_translation_runtime_service.py tests/test_agent_policy_service.py tests/test_source_build_service.py tests/test_api_source_build.py tests/test_source_discovery_service.py tests/test_source_build_agent.py tests/test_source_build_runtime_service.py tests/test_source_build_lifespan.py tests/test_canonical_content_service.py tests/test_content_distribution_service.py tests/test_api_client_reading.py tests/test_api_client_access.py tests/test_job_service.py tests/test_agent_runtime_service.py tests/test_api_agent_runs.py tests/test_agent_tool_registry.py tests/test_source_runtime_repo.py tests/test_source_health_scheduler.py tests/test_source_read_service.py tests/test_source_routing_service.py tests/test_rbac_permissions.py tests/test_engine_runtime_service.py tests/test_api_engine_runtime.py tests/test_api_provider_platform.py -q` -> `121 passed`.
  - Runtime check: `http://127.0.0.1:8000/api/status` -> `200`; `http://127.0.0.1:3000` -> `200`.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 LegadoHub 演进为 API Key 驱动的服务端内容生产、统一、路由与分发平台，并通过受控 Agent 实现自动写源、校准和作品知识处理。

**Architecture:** 保留现有 `/api`、FastAPI、SQLite repository、Legado runtime 与 ProviderPlatformService；在其上增加控制平面、可持久化 job、Agent 工具注册、规则版本与 Canonical 内容模型。所有下游访问通过 API Key 契约进入服务端，所有 Agent 输出均为可验证、可回滚的候选版本。

**Tech Stack:** Python 3.13、FastAPI、Pydantic、SQLAlchemy SQLite、现有 JavaScript/Legado runtime、React 18、TypeScript、Vitest、pytest。

---

## Sync Status (2026-07-12)

> Sync note: 下方 checkbox 保留原始实施脚本；当前执行状态以本节为准。

- **Overall:** Phase 1 ~ Phase 4 已有可运行骨架；Task 5、8、9 已补齐最小实现，Task 10 已补上 webhook retry/dedupe/failure history、due delivery dispatch、SSE recent replay、lifespan worker、前端 SSE 断线自动重连，以及前端 Agent Runs / Event Deliveries / Source Builds / Review Queue console 的最小闭环，并把 translation review / source version publish / persisted source review 候选并入 review queue，且 review queue 已支持 source version / knowledge proposal / translation job / source review 的 resolve 动作；Task 6 已补上“仅 review.resolve 可发布版本”的首版链路，Task 7 已进一步补上 source health regression 自动入 `source.build` discovery job、configured catalogs 自动 seed `source.build` discovery job、origin budget 实际接入 catalog discovery 调度 helper、source.build lifespan worker，以及 source.build job 自动修复结果回流到 agent run / candidate version / review queue 的最小闭环；前端 Source Builds 页面已修复为可展示 autonomous build 决策上下文，并已把 source.build runtime 的真实 probe/inspection 与规则候选补全：CompatibilityEngine 生成可执行 source_rule，SourceProbeService 采集 search/toc/content 摘要，runtime 生成 rule_patch、validation gate 与 canary/defer/escalate 决策并回流 agent run / candidate version / Source Builds 页面；catalog discovery 已按健康回归优先级排序并继续尊重 origin budget；Task 11 仍有范围差距。
- **Verification:**
  - `backend/.venv/Scripts/python.exe -m pytest tests/test_event_delivery_service.py tests/test_event_delivery_scheduler.py tests/test_event_delivery_lifespan.py -q` → `9 passed`
  - `backend/.venv/Scripts/python.exe -m pytest tests/test_source_build_runtime_service.py tests/test_api_source_build.py -q` → `13 passed`
  - `backend/.venv/Scripts/python.exe -m pytest tests/test_source_discovery_service.py tests/test_source_health_scheduler.py tests/test_source_build_runtime_service.py tests/test_api_source_build.py tests/test_source_build_lifespan.py -q` → `24 passed`
  - `backend/.venv/Scripts/python.exe -m pytest tests/test_event_delivery_service.py tests/test_event_delivery_scheduler.py tests/test_event_delivery_lifespan.py tests/test_runtime_bootstrap.py tests/test_api_health.py tests/test_work_knowledge_service.py tests/test_api_work_knowledge.py tests/test_translation_runtime_service.py tests/test_agent_policy_service.py tests/test_source_build_service.py tests/test_api_source_build.py tests/test_source_discovery_service.py tests/test_source_build_agent.py tests/test_source_build_runtime_service.py tests/test_source_build_lifespan.py tests/test_canonical_content_service.py tests/test_content_distribution_service.py tests/test_api_client_reading.py tests/test_api_client_access.py tests/test_job_service.py tests/test_agent_runtime_service.py tests/test_api_agent_runs.py tests/test_agent_tool_registry.py tests/test_source_runtime_repo.py tests/test_source_health_scheduler.py tests/test_source_read_service.py tests/test_source_routing_service.py tests/test_rbac_permissions.py tests/test_engine_runtime_service.py tests/test_api_engine_runtime.py tests/test_api_provider_platform.py -q` → `120 passed`
  - `npm test -- --run src/app/providers/ThemeProvider.test.tsx src/components/layout/AppConsoleShell.test.tsx src/features/sources/SourceListPage.test.tsx src/features/sources/SourceHealthPage.test.tsx src/features/sources/SourceHealthDetailPage.test.tsx src/features/engine/EngineRunsPage.test.tsx src/features/system/SystemSettingsPage.test.tsx src/features/auth/LoginPage.test.tsx src/app/router/guards.test.tsx src/features/operations/AgentRunsPage.test.tsx src/features/operations/JobsPage.test.tsx src/features/operations/EventDeliveriesPage.test.tsx src/features/operations/SourceBuildsPage.test.tsx src/features/operations/ReviewQueuePage.test.tsx` → `14 files, 25 tests passed`
  - `npm run build` → pass
  - `http://127.0.0.1:8000/api/status` → `200`
  - `http://127.0.0.1:3000` → `200`
- **Important drift:** Task 6 已补上“仅 `review.resolve` 可发布版本”的首版链路，并已有真实 probe 摘要、source_rule、rule_patch 与 validation gate 回填到 autonomous_build / agent tool evidence；更细粒度发布审计仍未完成；Task 7 已补齐 source health regression / build escalation 的 persisted review queue 首版，并补上 health regression 自动入 `source.build` discovery job、configured catalogs 自动 seed discovery job、origin budget 实际接入 catalog discovery 调度 helper、source.build lifespan worker，以及 source.build job 自动修复结果回流到 agent run / candidate version / review queue 的闭环；当前 source.build runtime 已在 payload 缺少 site_profile/evidence 时走 CompatibilityEngine + SourceProbeService 获取真实 search/toc/content 证据摘要并生成可执行规则候选；catalog discovery 已按健康回归优先级排序并继续尊重 origin budget；更完整人工处理工作流与站点特化 selector 合成仍未完成；Task 10 已补上 webhook retries、dedupe、durable failure history、due delivery dispatch、scheduler helper、SSE recent replay、lifespan worker、agent-runs/delivery/attempts/source-builds/review-queue 运维查询接口与前端 Agent Runs / Event Deliveries / Source Builds / Review Queue 页面，并新增前端 SSE 断线自动重连，且 Source Builds 页面已修复为显示 autonomous build 决策、validation 与 probe 摘要；但多租户长连接消费、背压治理，以及继续扩展更多 review item 类型的完整运维前端仍未完成；Task 11 已补到 character / plot / world proposals 与 translation review memory，但 agent tool review 发布链路、translation memory 深化与更完整知识模型仍未完成。

| Task | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Task 1 | 部分完成 | `test_api_client_access.py` 通过 | `/api/capabilities`、API Key job 提交与幂等已存在；但计划中的 `client_access_service.py` / `client_access_repo.py` / `require_api_capability()` / 统一 envelope 未按原拆分落地。 |
| Task 2 | 完成（实现有漂移） | `AuthProvider.test.tsx`、`guards.test.tsx` 通过 | 三秒超时、失败重试与重新登录已实现，但使用 `initializing` + `restoreFailed`，没有落成计划中的 `sessionState` finite-state API。 |
| Task 3 | 完成 | `test_job_service.py` 通过；`test_api_client_access.py` 覆盖 job API 流程 | durable jobs、lease reclaim、事件读取已在现有 `jobs.py` / `job_service.py` 内落地；计划中的 `test_api_jobs.py` 文件不存在。 |
| Task 4 | 完成 | `test_agent_runtime_service.py`、`test_agent_tool_registry.py` 通过 | Agent run、tool invocation/result/evidence 持久化与 registry 授权约束已存在。 |
| Task 5 | 完成 | `test_agent_policy_service.py` 通过 | 已新增 `AgentPolicyService` / `SiteProfileService`，覆盖 deterministic-first、受限 LLM context 与 budget/risk 阻断。 |
| Task 6 | 部分完成 | `test_source_build_service.py`、`test_api_source_build.py`、`test_engine_runtime_service.py`、`test_api_engine_runtime.py` 通过 | `/api/source-builds`、候选 rule version、URL 归一化与幂等 build job 已落地；source version 现需先经过 `/api/engine/reviews/{source_version_id}/resolve` 才能发布，`deploy` 仅创建 review 请求；真实 probe 摘要、source_rule、rule_patch 与 validation gate 回填已有首版，更细粒度发布审计仍未完成。 |
| Task 7 | 部分完成 | `test_source_discovery_service.py`、`test_source_build_service.py`、`test_source_build_agent.py`、`test_source_build_runtime_service.py`、`test_source_build_lifespan.py`、`test_source_health_scheduler.py`、`test_api_source_build.py` 通过 | 已补 discovery budget/circuit/backoff、build agent 的 canary/defer/escalate 决策、source health regression / build escalation 的持久化 source review queue 首版，以及 health regression 自动入 `source.build` discovery job、configured catalogs 自动 seed `source.build` discovery job、origin budget 实际接入 catalog discovery helper、source.build lifespan worker，并补上 source.build job 自动修复结果回流到 agent run / candidate version / review queue 的最小闭环；当前 source.build runtime 已在 payload 缺少 site_profile/evidence 时走 CompatibilityEngine + SourceProbeService 获取真实 search/toc/content 证据摘要，生成可执行 source_rule、rule_patch 与 validation gate，回写 agent run tool result/evidence 与 candidate version payload.autonomous_build；catalog discovery 已按健康回归优先级排序并继续尊重 origin budget；但更完整人工处理工作流与站点特化 selector 合成仍未完成。 |
| Task 8 | 完成（最小实现） | `test_canonical_content_service.py` 通过 | 已新增 canonical work / chapter / source chapter / variant / alignment 持久化与低置信度 review 标记；仍缺更复杂的 alias / anchor / author 融合策略。 |
| Task 9 | 完成（最小实现） | `test_content_distribution_service.py`、`test_api_client_reading.py` 通过 | `/api/client/works`、`/api/client/works/{work_id}`、`/toc`、`/chapters/{chapter_id}` 已落地，并记录 route decisions；tenant policy 与更细粒度 freshness/latency 仍是静态评分。 |
| Task 10 | 部分完成 | `test_event_delivery_service.py`、`test_event_delivery_scheduler.py`、`test_event_delivery_lifespan.py`、`test_api_agent_runs.py`、`AgentRunsPage.test.tsx`、`JobsPage.test.tsx`、`EventDeliveriesPage.test.tsx`、`SourceBuildsPage.test.tsx`、`ReviewQueuePage.test.tsx`、`test_api_provider_platform.py` 通过 | 已新增 webhook signature prepare、dedupe enqueue、retry/failure history 持久化、due webhook dispatch、scheduler helper、SSE recent replay、lifespan worker、agent-runs/delivery/attempts/source-builds/review-queue 运维查询接口，以及 Agent Runs / Event Deliveries / Source Builds / Review Queue 页面；前端已补上 SSE 断线自动重连，review queue 已并入 translation review、source version publish 与 persisted source review 候选，并支持 source version / knowledge proposal / translation job / source review 的 resolve 动作；多租户长连接治理、背压控制与继续扩展更多 review item 类型仍未落地。 |
| Task 11 | 部分完成 | `test_work_knowledge_service.py`、`test_api_work_knowledge.py`、`test_translation_runtime_service.py` 通过 | 已新增 character / plot / world proposals、review 发布、`content_variant_id` 翻译入口与 translation review memory；agent tool review 发布链路、translation memory 深化与更完整知识模型仍未完成。 |

## File Map

- `backend/app/domain/entities/`: 新增控制平面、Agent、规则版本、统一作品与知识实体。
- `backend/app/domain/repositories/`: 对应 repository 协议，保持 application 层不依赖 SQLite。
- `backend/app/infrastructure/persistence/sqlite/schema.py`: 新表和索引；创建幂等 schema upgrade 函数。
- `backend/app/infrastructure/persistence/sqlite/`: 各实体的 SQLite repository。
- `backend/app/application/services/`: API Key、job、Agent、写源、统一目录、分发、知识服务。
- `backend/app/interfaces/http/`: `/api` 新 routers 和统一 API Key dependency。
- `backend/app/infrastructure/persistence/factory.py`: 新 service/repository composition root。
- `frontend/src/api/modules/`、`features/`: 控制台 API Key、Agent、书源构建、校准、下游和知识管理页。
- `backend/tests/`、`frontend/src/**/*.test.tsx`: 单元、契约、权限、队列和页面行为测试。

## Phase 1: 控制平面与客户端契约

### Task 1: API Key client identity and capability contract

**Files:**
- Create: `backend/app/domain/entities/client_access.py`
- Create: `backend/app/domain/repositories/client_access_repo.py`
- Create: `backend/app/application/services/client_access_service.py`
- Create: `backend/app/interfaces/http/client_access.py`
- Modify: `backend/app/interfaces/http/deps.py`
- Modify: `backend/app/interfaces/http/router.py`
- Modify: `backend/app/core/permissions.py`
- Test: `backend/tests/test_client_access_service.py`
- Test: `backend/tests/test_api_client_access.py`

- [ ] **Step 1: Write failing API Key contract tests**

```python
def test_api_key_identity_exposes_only_granted_capabilities(client, seeded_key):
    response = client.get('/api/capabilities', headers={'Authorization': f'Bearer {seeded_key.raw}'})
    assert response.status_code == 200
    assert response.json()['data']['capabilities'] == ['read.work', 'read.toc']

def test_idempotency_key_returns_original_job(client, seeded_key):
    headers = {'Authorization': f'Bearer {seeded_key.raw}', 'Idempotency-Key': 'request-1'}
    first = client.post('/api/jobs', headers=headers, json={'capability': 'crawl.refresh', 'input': {'work_id': 'w1'}})
    second = client.post('/api/jobs', headers=headers, json={'capability': 'crawl.refresh', 'input': {'work_id': 'w1'}})
    assert first.json()['data']['job_id'] == second.json()['data']['job_id']
```

- [ ] **Step 2: Run RED tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_client_access_service.py tests/test_api_client_access.py -q`

Expected: FAIL because API Key client identity, capabilities and job idempotency do not exist.

- [ ] **Step 3: Implement API Key principal and envelope**

Define `ClientPrincipal(key_id, tenant_id, permissions, quota_scope)` and a `require_api_capability(capability)` dependency that accepts `lh_*` bearer keys. Return the same envelope fields from every client endpoint: `trace_id`, `status`, `result`, `usage`, `route_summary`, and optional `job_id`. Add permissions `client.capabilities.read`, `source.submit`, `read.work`, `read.toc`, `read.chapter`, `jobs.submit`, `events.read`.

- [ ] **Step 4: Run GREEN tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_client_access_service.py tests/test_api_client_access.py -q`

Expected: PASS.

### Task 2: Session recovery finite-state UI

**Files:**
- Modify: `frontend/src/app/providers/AuthProvider.tsx`
- Modify: `frontend/src/app/router/RequireAuth.tsx`
- Modify: `frontend/src/app/providers/AuthProvider.test.tsx`
- Modify: `frontend/src/app/router/guards.test.tsx`

- [ ] **Step 1: Write failing recovery state tests**

```tsx
expect(screen.getByText('正在恢复会话')).toBeVisible()
await waitFor(() => expect(screen.getByRole('button', { name: '重新登录' })).toBeVisible())
```

- [ ] **Step 2: Run RED tests**

Run: `npm test -- --run src/app/providers/AuthProvider.test.tsx src/app/router/guards.test.tsx`

Expected: FAIL because the provider exposes only a boolean and `RequireAuth` renders an unbounded `Restoring session` label.

- [ ] **Step 3: Implement bounded recovery**

Expose `sessionState: 'checking' | 'authenticated' | 'anonymous' | 'failed'`; race refresh and `/auth/me` against a three-second timeout; show progress during `checking`, a retry/login action during `failed`, and redirect only after `anonymous`. Do not persist access tokens.

- [ ] **Step 4: Run GREEN tests**

Run: `npm test -- --run src/app/providers/AuthProvider.test.tsx src/app/router/guards.test.tsx`

Expected: PASS.

### Task 3: Durable jobs, leases and events

**Files:**
- Create: `backend/app/domain/entities/job.py`
- Create: `backend/app/domain/repositories/job_repo.py`
- Create: `backend/app/application/services/job_service.py`
- Create: `backend/app/interfaces/http/jobs.py`
- Create: `backend/app/infrastructure/persistence/sqlite/job_repo_impl.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Modify: `backend/app/interfaces/http/router.py`
- Test: `backend/tests/test_job_service.py`
- Test: `backend/tests/test_api_jobs.py`

- [ ] **Step 1: Write failing lease and retry tests**

```python
def test_expired_lease_is_reclaimed_once(repo, clock):
    job = repo.enqueue(kind='crawl.refresh', idempotency_key='k1')
    first = repo.lease_next(worker_id='worker-a', now=clock.now())
    clock.advance(seconds=61)
    second = repo.lease_next(worker_id='worker-b', now=clock.now())
    assert first.id == second.id == job.id
    assert second.attempt_count == 2
```

- [ ] **Step 2: Run RED tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_job_service.py tests/test_api_jobs.py -q`

Expected: FAIL because durable jobs and leases do not exist.

- [ ] **Step 3: Implement job lifecycle**

Persist `queued`, `leased`, `succeeded`, `failed`, `cancelled`, `dead_letter`; enforce unique `(tenant_id, idempotency_key)` when supplied. Publish immutable tenant-scoped events, expose job read endpoints, and record usage/cost on completion. Use database transaction claims first; preserve a service boundary that can later use Redis/RabbitMQ.

- [ ] **Step 4: Run GREEN tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_job_service.py tests/test_api_jobs.py -q`

Expected: PASS.

## Phase 1.5: Agent Tool Runtime

### Task 4: Tool registry, authorization and evidence records

**Files:**
- Create: `backend/app/domain/entities/agent_runtime.py`
- Create: `backend/app/application/services/agent_runtime_service.py`
- Create: `backend/app/application/services/agent_tool_registry.py`
- Create: `backend/app/interfaces/http/agent_runs.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Test: `backend/tests/test_agent_runtime_service.py`
- Test: `backend/tests/test_agent_tool_registry.py`

- [ ] **Step 1: Write failing tool authorization tests**

```python
def test_source_build_agent_cannot_call_unregistered_shell_tool(registry):
    with pytest.raises(AuthorizationException):
        registry.invoke(agent_kind='source_build', tool_name='shell.exec', arguments={})

def test_knowledge_proposal_requires_evidence(registry):
    result = registry.invoke(agent_kind='knowledge', tool_name='knowledge.propose', arguments={'entity': {'name': 'Lin'}})
    assert result.status == 'rejected'
    assert result.error_code == 'evidence_required'
```

- [ ] **Step 2: Run RED tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_agent_runtime_service.py tests/test_agent_tool_registry.py -q`

Expected: FAIL because no tool registry or evidence policy exists.

- [ ] **Step 3: Implement constrained tools**

Create tool schemas for `work.*`, `toc.get`, `chapter.get`, `character.*`, `plot.*`, `world.*`, `evidence.*`, `source.*`, `rule.*`, `knowledge.propose`, `translation.propose`, and `review.*`. Persist `AgentRun`, `ToolInvocation`, `ToolResult`, and `ToolEvidence`; assign `read`, `propose`, or `operate` class; deny shell, unrestricted network, direct SQL, cross-tenant IDs, and publish actions.

- [ ] **Step 4: Run GREEN tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_agent_runtime_service.py tests/test_agent_tool_registry.py -q`

Expected: PASS.

### Task 5: Low-token planning policy and evaluation

**Files:**
- Create: `backend/app/application/services/agent_policy_service.py`
- Create: `backend/app/application/services/site_profile_service.py`
- Test: `backend/tests/test_agent_policy_service.py`

- [ ] **Step 1: Write failing deterministic-first tests**

```python
def test_policy_uses_template_match_without_model_call(policy, matching_profile):
    decision = policy.plan_source_repair(matching_profile, evidence={'dom_signature': 'sig-1'})
    assert decision.strategy == 'deterministic_patch'
    assert decision.model_budget == 0
```

- [ ] **Step 2: Run RED tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_agent_policy_service.py -q`

Expected: FAIL because no deterministic-first policy exists.

- [ ] **Step 3: Implement policy**

Score cache hit, site profile, template match, fixture coverage, confidence, budget and risk before allowing LLM invocation. Limit model context to structured evidence, sampled content and a patch candidate. Persist outcome tags so approved human corrections create reusable site profiles and repair patterns.

- [ ] **Step 4: Run GREEN tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_agent_policy_service.py -q`

Expected: PASS.

## Phase 2: Automated Source Building

### Task 6: Source rule versions and manual URL submission

**Files:**
- Create: `backend/app/domain/entities/source_rule_version.py`
- Create: `backend/app/application/services/source_build_service.py`
- Create: `backend/app/interfaces/http/source_build.py`
- Modify: `backend/app/interfaces/http/router.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Test: `backend/tests/test_source_build_service.py`
- Test: `backend/tests/test_api_source_build.py`

- [ ] **Step 1: Write failing manual submission tests**

```python
def test_manual_url_submission_creates_deduplicated_build_job(client, client_key):
    payload = {'url': 'https://example.test/books/', 'keyword': 'sample'}
    first = client.post('/api/source-builds', json=payload, headers=client_key.headers)
    second = client.post('/api/source-builds', json=payload, headers=client_key.headers)
    assert first.json()['data']['job_id'] == second.json()['data']['job_id']
```

- [ ] **Step 2: Run RED tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_source_build_service.py tests/test_api_source_build.py -q`

Expected: FAIL because source build submissions and rule versions do not exist.

- [ ] **Step 3: Implement source build lifecycle**

Normalize URL, deduplicate by canonical origin/path, create a `SourceRuleVersion(status='candidate')`, and enqueue `source.build`. Reuse existing Legado runtime behind `SourceAdapter`; store safe evidence for search/work/toc/content. Only `review.resolve` can move candidate to published; published version changes are auditable and reversible.

- [ ] **Step 4: Run GREEN tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_source_build_service.py tests/test_api_source_build.py -q`

Expected: PASS.

### Task 7: Discovery scheduler, repair loop and autonomous policy

**Files:**
- Create: `backend/app/application/services/source_discovery_service.py`
- Create: `backend/app/application/services/source_build_agent.py`
- Modify: `backend/app/application/services/source_health_service.py`
- Test: `backend/tests/test_source_discovery_service.py`
- Test: `backend/tests/test_source_build_agent.py`

- [ ] **Step 1: Write failing bounded discovery tests**

```python
def test_discovery_skips_open_circuit_and_respects_origin_budget(discovery, clock):
    discovery.enqueue_candidate('https://blocked.test')
    discovery.mark_origin_blocked('https://blocked.test', now=clock.now())
    assert discovery.next_jobs(now=clock.now()) == []
```

- [ ] **Step 2: Run RED tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_source_discovery_service.py tests/test_source_build_agent.py -q`

Expected: FAIL because discovery policy and patch repair loop do not exist.

- [ ] **Step 3: Implement safe autonomous building**

Create low-priority discovery jobs from source health regressions and configured catalogs. Enforce origin-level budgets, delay, exponential backoff and circuit breakers. `SourceBuildAgent` runs one patch per attempt, validates fixtures and real samples, chooses canary/defer/escalate through `AgentPolicyService`, and creates a review item whenever confidence, budget or safety thresholds fail.

- [ ] **Step 4: Run GREEN tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_source_discovery_service.py tests/test_source_build_agent.py -q`

Expected: PASS.

## Phase 3: Canonical Works and Multi-source Routing

### Task 8: Canonical work, chapter alignment and content variants

**Files:**
- Create: `backend/app/domain/entities/canonical_content.py`
- Create: `backend/app/application/services/canonical_content_service.py`
- Create: `backend/app/infrastructure/persistence/sqlite/canonical_content_repo_impl.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Test: `backend/tests/test_canonical_content_service.py`

- [ ] **Step 1: Write failing alignment tests**

```python
def test_aligns_source_chapter_by_order_title_and_neighbors(service):
    result = service.align_chapters(canonical=['Chapter 1', 'Chapter 2'], source=['01 Start', '02 Continue'])
    assert result.matches[0].confidence >= 0.8
    assert result.matches[0].canonical_index == 0
```

- [ ] **Step 2: Run RED tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_canonical_content_service.py -q`

Expected: FAIL because canonical records and alignment do not exist.

- [ ] **Step 3: Implement version-preserving canonicalization**

Persist `CanonicalWork`, `SourceWork`, `WorkAlias`, `CanonicalChapter`, `SourceChapter`, `ContentVariant`, and alignment evidence. Use normalized title/author, order, neighboring chapters and content anchors; never overwrite raw source records. Route low-confidence matches to review.

- [ ] **Step 4: Run GREEN tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_canonical_content_service.py -q`

Expected: PASS.

### Task 9: Route decisions and synchronous reading API

**Files:**
- Create: `backend/app/application/services/content_distribution_service.py`
- Create: `backend/app/interfaces/http/client_reading.py`
- Modify: `backend/app/interfaces/http/router.py`
- Test: `backend/tests/test_content_distribution_service.py`
- Test: `backend/tests/test_api_client_reading.py`

- [ ] **Step 1: Write failing fallback test**

```python
def test_reading_uses_next_healthy_variant_after_primary_failure(service):
    result = service.read_chapter(tenant_id='t1', chapter_id='c1')
    assert result.route_summary['fallback_count'] == 1
    assert result.result['source_id'] == 'healthy-source'
```

- [ ] **Step 2: Run RED tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_content_distribution_service.py tests/test_api_client_reading.py -q`

Expected: FAIL because client reading endpoints and decision history do not exist.

- [ ] **Step 3: Implement reading distribution**

Expose `/api/client/works`, `/api/client/works/{work_id}`, `/api/client/works/{work_id}/toc`, and `/api/client/chapters/{chapter_id}`. Select verified variants by tenant policy, health, coverage, quality, freshness and latency; persist every `RouteDecision`; never synchronously crawl a missing chapter.

- [ ] **Step 4: Run GREEN tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_content_distribution_service.py tests/test_api_client_reading.py -q`

Expected: PASS.

## Phase 4: Events, Webhooks and Console Operations

### Task 10: SSE/webhook delivery and operational pages

**Files:**
- Create: `backend/app/application/services/event_delivery_service.py`
- Create: `backend/app/interfaces/http/events.py`
- Create: `frontend/src/features/operations/JobsPage.tsx`
- Create: `frontend/src/features/operations/SourceBuildsPage.tsx`
- Create: `frontend/src/features/operations/ReviewQueuePage.tsx`
- Modify: `frontend/src/app/navigation.tsx`
- Modify: `frontend/src/app/router.tsx`
- Test: `backend/tests/test_event_delivery_service.py`
- Test: `frontend/src/features/operations/JobsPage.test.tsx`

- [ ] **Step 1: Write failing signed delivery test**

```python
def test_webhook_delivery_has_event_id_and_hmac_signature(delivery_service):
    delivery = delivery_service.prepare(event_type='chapter.ready', tenant_id='t1', payload={'chapter_id': 'c1'})
    assert delivery.headers['X-Legado-Event-Id'] == delivery.event_id
    assert delivery.headers['X-Legado-Signature'].startswith('sha256=')
```

- [ ] **Step 2: Run RED tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_event_delivery_service.py -q`

Expected: FAIL because signed delivery does not exist.

- [ ] **Step 3: Implement delivery and operations UI**

Deliver tenant-scoped events by SSE and signed webhook with retries, deduplication IDs and durable failure history. Build console pages for jobs, agent runs, source candidates and review queue, all protected by new RBAC permissions and using existing API client conventions.

- [ ] **Step 4: Run GREEN tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_event_delivery_service.py -q`

Run: `npm test -- --run src/features/operations/JobsPage.test.tsx`

Expected: PASS.

## Phase 5: Translation and Knowledge Tools

### Task 11: Evidence-backed translation, character, plot and world proposals

**Files:**
- Create: `backend/app/domain/entities/work_knowledge.py`
- Create: `backend/app/application/services/work_knowledge_service.py`
- Create: `backend/app/interfaces/http/work_knowledge.py`
- Modify: `backend/app/application/services/translation_service.py`
- Modify: `backend/app/interfaces/http/router.py`
- Test: `backend/tests/test_work_knowledge_service.py`
- Test: `backend/tests/test_api_work_knowledge.py`

- [ ] **Step 1: Write failing evidence and review tests**

```python
def test_character_relation_is_candidate_until_reviewed(service):
    proposal = service.propose_relation(work_id='w1', source_chapter_id='c1', evidence='Lin trusts Mei', relation='trusts')
    assert proposal.status == 'candidate'
    assert service.list_published_relations('w1') == []
```

- [ ] **Step 2: Run RED tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_work_knowledge_service.py tests/test_api_work_knowledge.py -q`

Expected: FAIL because evidence-backed knowledge proposals do not exist.

- [ ] **Step 3: Implement knowledge and translation integration**

Make translation consume an explicit `ContentVariant`. Persist translation segments, variants, memory and reviews. Persist character aliases/relations, plot events/threads, world entities/rules and evidence; agent tools can create candidates only; `review.resolve` publishes an immutable revision.

- [ ] **Step 4: Run GREEN tests**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_work_knowledge_service.py tests/test_api_work_knowledge.py -q`

Expected: PASS.

## Final Verification

- [ ] Run the complete backend suite: `backend/.venv/Scripts/python.exe -m pytest -q`.
- [ ] Run the complete frontend suite: `npm test -- --run` from `frontend`.
- [ ] Build the frontend: `npm run build` from `frontend`.
- [ ] Run an API Key end-to-end flow: capability discovery, manual URL submission, job polling, candidate rule review, canonical work read, SSE or webhook event verification, and a knowledge proposal requiring review.
- [ ] Record Phase 1 through Phase 5 evidence in `docs/superpowers/reports/checkpoints/` before enabling autonomous canary actions.
