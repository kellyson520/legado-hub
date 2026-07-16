# Unified Source Audit Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every source candidate pass one durable probe-and-review-agent workflow before an administrator can publish it.

**Architecture:** A workflow service initializes and schedules the same audit record for generated, imported, drafted, and repaired candidates. The worker persists probe evidence, invokes a constrained review agent, and transitions that record to either `approved_for_publish` or a manual-review state. Publication consumes this record as its only approval authority.

**Tech Stack:** FastAPI, Python 3.12, SQLite/SQLAlchemy repositories, existing JobWorker, AgentRuntimeService, OpenAI-compatible tool calling, React/Vitest.

---

### Task 1: Queue every candidate through one audit service

**Files:**
- Create: `backend/app/application/services/source_audit_workflow_service.py`
- Modify: `backend/app/application/services/source_build_service.py`
- Modify: `backend/app/application/services/source_runtime_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Test: `backend/tests/test_source_audit_workflow_service.py`
- Test: `backend/tests/test_api_source_import_export.py`

- [ ] **Step 1: Write the failing scheduling tests**

```python
def test_schedule_candidate_initializes_queued_audit_and_idempotent_job():
    result = workflow.schedule(version_id='candidate-1', actor_id='42', trigger='import')
    assert result['status'] == 'queued'
    assert runtime.get_version('candidate-1').payload['source_audit']['job_id'] == result['job_id']

def test_imported_candidates_each_receive_one_audit_job():
    result = await service.import_legado_sources([source_a, source_b], actor_id='42')
    assert result['audit_queued'] == 2
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest backend/tests/test_source_audit_workflow_service.py backend/tests/test_api_source_import_export.py -q`

Expected: FAIL because the workflow service and import scheduling result do not exist.

- [ ] **Step 3: Implement scheduling**

```python
ACTIVE = frozenset({'queued', 'probing', 'reviewing'})

def schedule(self, *, version_id: str, actor_id: str, trigger: str) -> dict:
    version = self._runtime.get_version(version_id)
    audit = dict(version.payload.get('source_audit') or {})
    if audit.get('status') in ACTIVE and audit.get('job_id'):
        return {'source_version_id': version_id, 'status': audit['status'], 'job_id': audit['job_id']}
    job = self._build.submit_existing_candidate(version.id, actor_id, version.source_id, trigger)
    audit.update({'status': 'queued', 'job_id': job.id, 'trigger': trigger, 'reason_code': None})
    self._runtime.update_version_payload(version.id, {**version.payload, 'source_audit': audit})
    return {'source_version_id': version.id, 'status': 'queued', 'job_id': job.id}
```

Add `submit_existing_candidate` with idempotency key `source.audit:<version-id>`. Inject the workflow through the factory, then call it from `generate`, `import_legado_sources`, `create_rule_draft`, and `repair`. Bulk import queues after its single bulk insert and never probes inside the request.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest backend/tests/test_source_audit_workflow_service.py backend/tests/test_api_source_import_export.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/services/source_audit_workflow_service.py backend/app/application/services/source_build_service.py backend/app/application/services/source_runtime_service.py backend/app/infrastructure/persistence/factory.py backend/tests/test_source_audit_workflow_service.py backend/tests/test_api_source_import_export.py
git commit -m "feat: queue every source candidate for unified audit"
```

### Task 2: Add the evidence-only review agent to the audit worker

**Files:**
- Create: `backend/app/application/services/source_audit_review_agent_service.py`
- Modify: `backend/app/application/services/source_build_audit_service.py`
- Modify: `backend/app/application/services/source_review_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Test: `backend/tests/test_source_audit_review_agent_service.py`
- Test: `backend/tests/test_source_build_audit_service.py`

- [ ] **Step 1: Write failing review tests**

```python
@pytest.mark.asyncio
async def test_passing_probe_requires_agent_tool_evidence_for_approval():
    result = await audit.audit('candidate-1')
    assert result['status'] == 'approved_for_publish'
    assert result['review_agent_run_id'] == 'review-run-1'

@pytest.mark.asyncio
async def test_unavailable_agent_creates_one_manual_review_item():
    result = await audit.audit('candidate-1')
    assert result['status'] == 'manual_review_required'
    assert review.items[0].review_type == 'source_audit_manual_review'
```

- [ ] **Step 2: Run tests and verify RED**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest backend/tests/test_source_audit_review_agent_service.py backend/tests/test_source_build_audit_service.py -q`

Expected: FAIL because a passed probe currently returns `passed` without calling a review agent.

- [ ] **Step 3: Implement the review agent and status transitions**

Create `SourceAuditReviewAgentService.review(...)` with prompt version `source-audit-review/v1`. It can invoke only `source.inspect`, `source.probe`, `page.inspect`, `page.request`, `rule.validate`, and `review.request`; it has no publish tool. Approval requires accepted `source.probe`, `rule.validate`, and `review.request` results and records the Agent run plus tool-evidence ids.

Change `SourceBuildAuditService.audit` to persist `probing`, then `reviewing`, and finally `approved_for_publish`. Parser failure, model/provider unavailability, timeout, malformed tool calls, or incomplete evidence becomes `manual_review_required`; a negative verdict becomes `rejected`. Add idempotent `enqueue_manual_audit_review` with reason code, probe report, agent run id, and evidence ids.

- [ ] **Step 4: Run audit and worker tests and verify GREEN**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest backend/tests/test_source_audit_review_agent_service.py backend/tests/test_source_build_audit_service.py backend/tests/test_source_build_audit_scheduler.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/services/source_audit_review_agent_service.py backend/app/application/services/source_build_audit_service.py backend/app/application/services/source_review_service.py backend/app/infrastructure/persistence/factory.py backend/tests/test_source_audit_review_agent_service.py backend/tests/test_source_build_audit_service.py backend/tests/test_source_build_audit_scheduler.py
git commit -m "feat: require review agent evidence for source approval"
```

### Task 3: Enforce the unified publish gate and expose its reason

**Files:**
- Modify: `backend/app/application/services/source_runtime_service.py`
- Modify: `backend/app/interfaces/http/sources.py`
- Test: `backend/tests/test_source_rule_editor_service.py`
- Test: `backend/tests/test_api_source_build.py`

- [ ] **Step 1: Write failing publication tests**

```python
@pytest.mark.asyncio
async def test_publish_rejects_candidate_without_audit():
    with pytest.raises(ValidationException, match='source audit is missing'):
        await service.publish_rule_version('candidate-1', actor_id='admin')

@pytest.mark.asyncio
async def test_publish_accepts_approved_audit_with_settled_probe():
    assert (await service.publish_rule_version('candidate-1', actor_id='admin'))['status'] == 'published'
```

- [ ] **Step 2: Run tests and verify RED**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest backend/tests/test_source_rule_editor_service.py backend/tests/test_api_source_build.py -q`

Expected: FAIL because missing audit data is currently allowed through `_assert_source_audit_publishable`.

- [ ] **Step 3: Implement the strict gate**

```python
def _assert_source_audit_publishable(self, version) -> None:
    audit = version.payload.get('source_audit') if isinstance(version.payload, dict) else None
    if not isinstance(audit, dict):
        raise ValidationException('source audit is missing; queue audit before publication')
    if audit.get('status') != 'approved_for_publish':
        raise ValidationException(f"source audit blocks publication: {audit.get('reason_code') or audit.get('status')}")
    if audit.get('test_run_pending'):
        raise ValidationException('source audit test-run checkpoint must settle before publication')
```

Serialize `audit_status`, `audit_reason_code`, `audit_job_id`, and `manual_review_item_id` in source-version details and blocked publish responses.

- [ ] **Step 4: Run publish/API tests and verify GREEN**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest backend/tests/test_source_rule_editor_service.py backend/tests/test_api_source_build.py backend/tests/test_api_source_import_export.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/services/source_runtime_service.py backend/app/interfaces/http/sources.py backend/tests/test_source_rule_editor_service.py backend/tests/test_api_source_build.py
git commit -m "fix: block source publication until audit approval"
```

### Task 4: Render the same lifecycle in the console and migrate legacy candidates

**Files:**
- Modify: `frontend/src/api/modules/runtime-platform.ts`
- Modify: `frontend/src/features/operations/SourceBuildsPage.tsx`
- Modify: `frontend/src/features/sources/SourceRuleEditorPage.tsx`
- Modify: `backend/app/interfaces/http/events.py`
- Modify: `backend/app/application/services/source_audit_workflow_service.py`
- Test: `frontend/src/features/operations/SourceBuildsPage.test.tsx`
- Test: `frontend/src/features/sources/SourceRuleEditorPage.test.tsx`
- Test: `backend/tests/test_source_audit_workflow_service.py`

- [ ] **Step 1: Write failing UI and legacy tests**

```tsx
expect(await screen.findByText('审核 Agent：审核中')).toBeInTheDocument()
expect(screen.getByText('需人工审核：模型不可用')).toBeInTheDocument()
expect(screen.getByRole('button', { name: '发布书源' })).toBeDisabled()
```

```python
def test_reschedule_legacy_candidate_without_audit_creates_one_queued_job():
    assert workflow.reschedule_legacy_candidates(limit=100) == {'scheduled': 1, 'skipped': 0}
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/pytest backend/tests/test_source_audit_workflow_service.py -q
npm test -- --run src/features/operations/SourceBuildsPage.test.tsx src/features/sources/SourceRuleEditorPage.test.tsx
```

Expected: FAIL because the console infers old statuses and no legacy reschedule operation exists.

- [ ] **Step 3: Implement one DTO/status mapping and bounded migration**

Expose `sourceAudit` with the new status, reason, job id, agent run id, and review-item id. Map it to `排队中`, `探针验证中`, `审核 Agent 审核中`, `可发布`, `需人工审核`, and `已驳回`; only `approved_for_publish` enables publish. Add authenticated operations endpoint `POST /api/operations/source-audits/reschedule-legacy?limit=100`, which schedules only candidate versions with no active or approved audit and never changes published versions.

- [ ] **Step 4: Run complete verification and deploy**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/pytest backend/tests/test_source_audit_workflow_service.py backend/tests/test_source_audit_review_agent_service.py backend/tests/test_source_build_audit_service.py backend/tests/test_source_build_audit_scheduler.py backend/tests/test_api_source_import_export.py backend/tests/test_api_source_build.py backend/tests/test_source_rule_editor_service.py -q
npm test -- --run src/features/operations/SourceBuildsPage.test.tsx src/features/sources/SourceRuleEditorPage.test.tsx
npm run build
```

Expected: all commands exit 0. Build the release frontend, restart the backend retaining `backend/.env`, call the bounded reschedule endpoint, and verify one candidate follows `queued → probing → reviewing → manual_review_required` when the review provider is unavailable.

- [ ] **Step 5: Commit and push**

```bash
git add frontend/src/api/modules/runtime-platform.ts frontend/src/features/operations/SourceBuildsPage.tsx frontend/src/features/sources/SourceRuleEditorPage.tsx frontend/src/features/operations/SourceBuildsPage.test.tsx frontend/src/features/sources/SourceRuleEditorPage.test.tsx backend/app/interfaces/http/events.py backend/app/application/services/source_audit_workflow_service.py backend/tests/test_source_audit_workflow_service.py
git commit -m "feat: surface unified source audit lifecycle"
git push origin main
```
