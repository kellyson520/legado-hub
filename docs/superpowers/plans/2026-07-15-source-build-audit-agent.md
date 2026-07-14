# Source-Build Audit Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically run a real, bounded Legado reading audit after each source build and repair a failed candidate no more than four additional times before terminal review.

**Architecture:** `SourceBuildAuditService` probes the persisted candidate rule with a fresh `SourceProbeService`, records a `SourceTestRun`, and writes a bounded audit report into the candidate payload. It queues same-version source-build repairs until attempt five; terminal failures become source-review items. The source-build scheduler invokes audit after its existing runtime handler, while the existing review queue and operations views surface audit evidence and enforce audit-gated publication.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy SQLite, asyncio, existing Legado `SourceProbeService`, React, TypeScript, pytest, Vitest.

---

## File Structure

- Create `backend/app/application/services/source_build_audit_service.py` for fresh-client full-chain verification, scoring, bounded retry decisions, and persistence.
- Create `backend/tests/test_source_build_audit_service.py` for all audit state transitions.
- Modify `backend/app/application/services/source_build_service.py` to create the pending marker and enqueue same-version audit repairs.
- Modify `backend/app/application/services/source_review_service.py` for terminal audit review items.
- Modify `backend/app/application/services/source_runtime_service.py` and `backend/tests/test_api_source_build.py` for audit-gated publishing and queue serialization.
- Modify `backend/app/infrastructure/persistence/factory.py` and `backend/app/tasks/scheduler.py` to compose and invoke the audit service.
- Modify `backend/tests/test_source_health_scheduler.py` for scheduler integration.
- Modify `frontend/src/api/modules/operations.ts`, `frontend/src/features/operations/SourceBuildsPage.tsx`, `frontend/src/features/operations/SourceBuildsPage.test.tsx`, `frontend/src/features/operations/ReviewQueuePage.tsx`, and `frontend/src/features/operations/ReviewQueuePage.test.tsx` for audit evidence in operations UI.

### Task 1: Implement audit evidence and retry decisions

**Files:**
- Create: `backend/app/application/services/source_build_audit_service.py`
- Create: `backend/tests/test_source_build_audit_service.py`
- Modify: `backend/app/application/services/source_build_service.py`
- Modify: `backend/app/application/services/source_review_service.py`

- [ ] **Step 1: Write a failing passing-audit test.**

```python
@pytest.mark.asyncio
async def test_audit_pass_records_real_chain_evidence_and_test_run(...):
    result = await service.audit_candidate(version.id, tenant_id='builder', keyword='小说')
    assert result['status'] == 'passed'
    assert result['attempt'] == 1
    assert result['stages']['content']['content_length'] == 160
    assert repo.list_test_runs(version.id)[0].trigger == 'source_audit'
```

- [ ] **Step 2: Run RED.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_build_audit_service.py -q`

Expected: FAIL because `SourceBuildAuditService` does not exist.

- [ ] **Step 3: Implement the smallest passing audit path.**

```python
async def audit_candidate(self, source_version_id: str, *, tenant_id: str, keyword: str = '') -> dict:
    version = self._require_candidate(source_version_id)
    attempt = self._next_attempt(version.payload)
    evidence = await self._probe(self._source_rule(version), self._keywords(version.payload, keyword))
    report = self._build_report(evidence, attempt=attempt)
    self._repo.record_test_run(version.id, 'source_audit', report['score'], report['grade'], report['stages'], report['diagnostics'])
    return self._persist_pass(version, report) if report['passed'] else self._persist_failure(version, report, tenant_id)
```

`_build_report` requires successful non-empty search and TOC titles/hits, at least 80 content characters, a non-empty TOC chapter title, stage latency at most 10,000 ms, and total latency at most 25,000 ms. It returns only compact stage metadata and safe diagnostics.

- [ ] **Step 4: Verify GREEN.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_build_audit_service.py::test_audit_pass_records_real_chain_evidence_and_test_run -q`

Expected: PASS.

- [ ] **Step 5: Write and run RED tests for first failure, terminal fifth failure, and missing rule.**

```python
assert (await service.audit_candidate(version.id, tenant_id='builder'))['status'] == 'retry_queued'
assert jobs.list_jobs()[0].payload['source_version_id'] == version.id
assert terminal['status'] == 'failed'
assert review_items[0].review_type == 'source_audit_failed'
assert missing_rule['reason'] == 'missing_source_rule'
```

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_build_audit_service.py -q`

Expected: FAIL until retry and terminal paths are added.

- [ ] **Step 6: Implement bounded same-version repair and terminal review.**

Add `SourceBuildService.submit_audit_repair()` that enqueues a `source.build` job for the existing candidate using `source.audit.repair:<version-id>:attempt-<next-attempt>`. Add `SourceReviewService.enqueue_audit_failure()` with `review_type='source_audit_failed'`. Retain at most five history reports in `payload.source_audit`; on attempts 1–4 write `retry_queued`, and on attempt 5 call `update_version_status(version.id, 'failed')`, persist the review item, and return without enqueueing a job.

- [ ] **Step 7: Verify GREEN and commit.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_build_audit_service.py tests/test_source_build_service.py -q`

Expected: PASS.

Commit: `git add backend/app/application/services/source_build_audit_service.py backend/app/application/services/source_build_service.py backend/app/application/services/source_review_service.py backend/tests/test_source_build_audit_service.py backend/tests/test_source_build_service.py && git commit -m "feat: add bounded source build audit retries"`

### Task 2: Wire audit to the source-build worker and publication gate

**Files:**
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/tasks/scheduler.py`
- Modify: `backend/app/application/services/source_runtime_service.py`
- Modify: `backend/tests/test_source_health_scheduler.py`
- Modify: `backend/tests/test_api_source_build.py`

- [ ] **Step 1: Write failing scheduler and publication-gate tests.**

```python
result = await run_source_build_job(limit=1)
assert result['jobs'][0]['audit_result']['status'] == 'passed'
with pytest.raises(ValidationException, match='source audit'):
    await runtime.resolve_review(pending_version.id, reviewer_id='1', action='publish')
```

- [ ] **Step 2: Run RED.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_health_scheduler.py tests/test_api_source_build.py -q`

Expected: FAIL because the worker does not invoke the audit and review ignores its status.

- [ ] **Step 3: Compose and invoke the audit service.**

```python
def build_source_build_audit_service() -> SourceBuildAuditService:
    return SourceBuildAuditService(
        runtime_repo=build_source_runtime_repository(),
        probe_factory=build_source_probe_service,
        build_service=build_source_build_service(),
        review_service=build_source_review_service(),
    )

outcomes[job.id] = runtime.handle_job(job)
outcomes[job.id]['audit_result'] = await audit.audit_candidate(
    job.payload['source_version_id'], tenant_id=job.tenant_id, keyword=job.payload.get('keyword', ''),
)
```

Create the `source_audit` pending marker during `SourceBuildService.submit()`. In `SourceRuntimeService.resolve_review()`, when a marker is present, require `status == 'passed'` before publishing; leave unmarked legacy/manual versions compatible.

- [ ] **Step 4: Verify GREEN and commit.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_build_audit_service.py tests/test_source_health_scheduler.py tests/test_api_source_build.py tests/test_source_build_runtime_service.py -q`

Expected: PASS.

Commit: `git add backend/app/infrastructure/persistence/factory.py backend/app/tasks/scheduler.py backend/app/application/services/source_build_service.py backend/app/application/services/source_runtime_service.py backend/tests/test_source_health_scheduler.py backend/tests/test_api_source_build.py && git commit -m "feat: audit source builds before review publish"`

### Task 3: Expose audit trace in operations UI

**Files:**
- Modify: `frontend/src/api/modules/operations.ts`
- Modify: `frontend/src/features/operations/SourceBuildsPage.tsx`
- Modify: `frontend/src/features/operations/SourceBuildsPage.test.tsx`
- Modify: `frontend/src/features/operations/ReviewQueuePage.tsx`
- Modify: `frontend/src/features/operations/ReviewQueuePage.test.tsx`
- Modify: `backend/app/interfaces/http/events.py`
- Modify: `backend/tests/test_api_source_build.py`

- [ ] **Step 1: Write failing API and component tests for audit evidence.**

```tsx
expect(screen.getByText('Audit: passed · 1/5 · A')).toBeInTheDocument()
expect(screen.getByText('search/toc/content: ok / ok / ok · 480ms')).toBeInTheDocument()
expect(screen.getByText('content parse failed')).toBeInTheDocument()
```

The API test must assert a source-version queue row includes the candidate `source_audit` payload and a terminal source-review row exposes `audit_report` evidence.

- [ ] **Step 2: Run RED.**

Run: `cd frontend && node node_modules/vitest/vitest.mjs run src/features/operations/SourceBuildsPage.test.tsx src/features/operations/ReviewQueuePage.test.tsx`

Expected: FAIL because no audit summary is rendered.

- [ ] **Step 3: Add typed audit view data and accessible rendering.**

Add a typed optional `SourceBuildAuditSummary` to `OperationSourceBuildRow.payload`. Render a compact text-first Audit column in Source Builds and include the same summary beneath source-version/source-review queue rows. Use explicit status/attempt text and existing semantic tables; preserve focusable action buttons and add `role='alert'` only for terminal failure notices.

- [ ] **Step 4: Verify GREEN and commit.**

Run: `cd frontend && node node_modules/vitest/vitest.mjs run src/features/operations/SourceBuildsPage.test.tsx src/features/operations/ReviewQueuePage.test.tsx && node node_modules/typescript/bin/tsc --noEmit`

Expected: PASS.

Commit: `git add frontend/src/api/modules/operations.ts frontend/src/features/operations/SourceBuildsPage.tsx frontend/src/features/operations/SourceBuildsPage.test.tsx frontend/src/features/operations/ReviewQueuePage.tsx frontend/src/features/operations/ReviewQueuePage.test.tsx backend/app/interfaces/http/events.py backend/tests/test_api_source_build.py && git commit -m "feat: show source audit traces in operations"`

### Task 4: Verify the complete audit loop

**Files:**
- Verify only: files in Tasks 1–3 and `backend/scripts/smoke_source_to_insight.py`.

- [ ] **Step 1: Run focused backend verification.**

Run: `cd backend && /tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_build_audit_service.py tests/test_source_build_service.py tests/test_source_build_runtime_service.py tests/test_source_health_scheduler.py tests/test_api_source_build.py tests/test_source_probe_service.py -q`

Expected: PASS without unclosed-client warnings.

- [ ] **Step 2: Run focused frontend verification and production build.**

Run: `cd frontend && node node_modules/vitest/vitest.mjs run src/features/operations/SourceBuildsPage.test.tsx src/features/operations/ReviewQueuePage.test.tsx && node node_modules/typescript/bin/tsc --noEmit && node node_modules/vite/bin/vite.js build`

Expected: PASS.

- [ ] **Step 3: Run the Agent-off real-site smoke.**

Run: `cd backend && DB_PATH=/tmp/source-audit-off.sqlite /tmp/legado-hub-pytest-venv/bin/python scripts/smoke_source_to_insight.py --source-url https://www.biquga.com/list/0/1.html --book-name '斗罗大陆' --author-hint '唐家三少' --tenant-id source-audit-off --output /tmp/source-audit-off.json`

Expected: deterministic source build succeeds; its audit report contains a real search/TOC/content trace and does not invoke a model.

- [ ] **Step 4: Inspect the scoped diff and request review.**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only task files are staged for the audit commits and pre-existing unrelated changes remain untouched.
