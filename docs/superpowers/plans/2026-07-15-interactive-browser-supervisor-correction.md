# Interactive Browser Supervisor Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a manually verified source build usable from its worker-created session through browser relay, validation, expiry, and audit acceptance without cross-event-loop access or terminal-state races.

**Architecture:** A process-local, dedicated supervisor event loop owns all Playwright handles, expiry tasks, and driver cleanup. Callers from source-build worker threads and HTTP request loops use an async façade that submits work to that owner loop; raw handles remain memory-only. SQLite state transitions use compare-and-set updates, while the source audit acceptance callback executes before a successful session is terminally closed.

**Tech Stack:** FastAPI, asyncio, threading, SQLAlchemy/SQLite, Playwright, pytest.

---

## File structure

| Path | Responsibility |
| --- | --- |
| `backend/app/application/services/interactive_browser_supervisor.py` | Own a dedicated event-loop thread and forward all browser lifecycle calls to it. |
| `backend/app/application/services/interactive_browser_service.py` | Core loop-affine state machine: manual browser start, automatic flow locks, expiry, terminal cleanup. |
| `backend/app/domain/repositories/interactive_browser_repo.py` | Atomic state-transition and relay-token consumption repository contracts. |
| `backend/app/infrastructure/persistence/sqlite/interactive_browser_repo_impl.py` | Conditional SQLite UPDATE implementations for state/token consumption. |
| `backend/app/infrastructure/persistence/factory.py` | Cache one process-local supervisor, not a bare loop-affine service. |
| `backend/app/interfaces/http/interactive_browser.py` | Await supervisor operations and map expected unavailable/conflict cases safely. |
| `backend/tests/test_interactive_browser_supervisor.py` | Cross-loop worker/HTTP façade regression tests. |
| `backend/tests/test_interactive_browser_service.py` | Manual-only start, terminal cancel, automatic race, and expiry cases. |
| `backend/tests/test_interactive_browser_repo.py` | Concurrent one-time relay-token consumption regression. |
| `backend/tests/test_api_interactive_browser.py` | HTTP unavailable/conflict mapping coverage. |
| `backend/tests/test_source_build_audit_scheduler.py` | Worker scheduler to browser supervisor ownership regression. |

### Task 1: Move browser handles to a dedicated long-lived supervisor loop

**Files:**
- Create: `backend/app/application/services/interactive_browser_supervisor.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Test: `backend/tests/test_interactive_browser_supervisor.py`
- Test: `backend/tests/test_source_build_audit_scheduler.py`

- [ ] **Step 1: Write the cross-loop failing test**

```python
@pytest.mark.asyncio
async def test_supervisor_uses_one_owner_loop_from_worker_audit_and_http_continue():
    driver = LoopRecordingDriver()
    supervisor = InteractiveBrowserSupervisor.create_for_test(driver=driver, settings=EnabledSettings())
    await asyncio.to_thread(lambda: asyncio.run(supervisor.attempt_automatic(...)))
    await supervisor.continue_validation(...)
    assert len(set(driver.call_loop_ids)) == 1
```

- [ ] **Step 2: Run the test and verify the current direct-service design fails**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest -q tests/test_interactive_browser_supervisor.py::test_supervisor_uses_one_owner_loop_from_worker_audit_and_http_continue`

Expected: FAIL because no supervisor exists or the driver runs on caller loops.

- [ ] **Step 3: Implement the loop-affine façade**

```python
class InteractiveBrowserSupervisor:
    async def attempt_automatic(self, **kwargs):
        return await self._submit(self._core.attempt_automatic(**kwargs))

    async def continue_validation(self, *args, **kwargs):
        return await self._submit(self._core.continue_validation(*args, **kwargs))
```

Start one daemon thread with `asyncio.new_event_loop()` and `run_forever()`. Construct `InteractiveBrowserService` inside that loop. Submit coroutines using `asyncio.run_coroutine_threadsafe` and await them with `asyncio.wrap_future`; do not return a browser handle. Cache this façade in `build_interactive_browser_service`; provide a test-only cache reset path. The process shutdown hook must stop the loop and close remaining sessions.

- [ ] **Step 4: Verify the cross-loop test passes**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest -q tests/test_interactive_browser_supervisor.py tests/test_source_build_audit_scheduler.py`

Expected: PASS; the browser driver records one supervisor-loop identity even when audit originates in `asyncio.to_thread`.

### Task 2: Make terminal transitions and relay consumption race-safe

**Files:**
- Modify: `backend/app/domain/repositories/interactive_browser_repo.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/interactive_browser_repo_impl.py`
- Modify: `backend/app/application/services/interactive_browser_service.py`
- Test: `backend/tests/test_interactive_browser_repo.py`
- Test: `backend/tests/test_interactive_browser_service.py`

- [ ] **Step 1: Write failing terminal and token race tests**

```python
@pytest.mark.asyncio
async def test_cancel_cannot_overwrite_succeeded_or_failed_session(service):
    for state in (InteractiveBrowserState.SUCCEEDED, InteractiveBrowserState.FAILED):
        session = service.repo.create(session_with(state))
        with pytest.raises(ValueError, match='not_cancellable'):
            await service.cancel(session.id, owner_id=session.owner_id)

def test_relay_token_can_be_consumed_once_under_competing_transactions(repo):
    assert consume_from_two_isolated_sessions(repo) == 1
```

- [ ] **Step 2: Run the tests and verify current state overwrite/select-then-write behaviour fails**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest -q tests/test_interactive_browser_service.py::test_cancel_cannot_overwrite_succeeded_or_failed_session tests/test_interactive_browser_repo.py::test_relay_token_can_be_consumed_once_under_competing_transactions`

Expected: FAIL because terminal states are overwritten or both consumers receive the relay session.

- [ ] **Step 3: Add conditional repository updates and enforce them**

```python
def transition_state(self, session_id, *, expected_states, state, **fields):
    result = db.query(Model).filter(Model.id == session_id, Model.state.in_(expected_states)).update(values)
    if result != 1:
        return None
    db.commit()
    return self.get(session_id)
```

Consume a relay token with a single conditional `UPDATE` constrained by digest, owner, `consumed_at IS NULL`, and unexpired time; read the session only after exactly one row was updated. Cancel only transitions `AWAITING_MANUAL`; automatic and manual validation use per-session locks plus CAS. Never transition terminal `SUCCEEDED`, `FAILED`, `CANCELLED`, or `EXPIRED` back to another terminal state.

- [ ] **Step 4: Verify tests pass**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest -q tests/test_interactive_browser_repo.py tests/test_interactive_browser_service.py`

Expected: PASS.

### Task 3: Start manual-only sessions and protect automatic full-chain validation

**Files:**
- Modify: `backend/app/application/services/interactive_browser_service.py`
- Test: `backend/tests/test_interactive_browser_service.py`

- [ ] **Step 1: Write failing manual-only and automatic race tests**

```python
@pytest.mark.asyncio
async def test_automatic_disabled_starts_browser_before_waiting_for_manual(service, driver):
    session = await service.start_or_resume(...)
    assert session.state == InteractiveBrowserState.AWAITING_MANUAL
    assert driver.start_calls == 1
    assert session.id in service._handles

@pytest.mark.asyncio
async def test_automatic_full_chain_cannot_revive_expired_session(service, deferred_probe):
    task = asyncio.create_task(service.attempt_automatic(...))
    await deferred_probe.started.wait()
    await service.expire_session(session_id)
    deferred_probe.finish_success()
    assert (await task).state == 'unavailable'
    assert service.repo.get(session_id).state == InteractiveBrowserState.EXPIRED
```

- [ ] **Step 2: Run tests and verify both current behaviours fail**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest -q tests/test_interactive_browser_service.py::test_automatic_disabled_starts_browser_before_waiting_for_manual tests/test_interactive_browser_service.py::test_automatic_full_chain_cannot_revive_expired_session`

Expected: FAIL because manual-only starts no driver and automatic uses an unconditional success update.

- [ ] **Step 3: Implement bounded manual start and automatic locking**

For `automatic_enabled=False`, start the ordinary browser/profile with the same target origin and enter `AWAITING_MANUAL` without invoking automatic probe. During automatic full-chain validation, hold the per-session lock, constrain the probe to remaining session time, and complete using `transition_state(expected_states=(SUCCEEDED,))`; if it fails, return unavailable and leave the terminal state untouched.

- [ ] **Step 4: Verify tests pass**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest -q tests/test_interactive_browser_service.py`

Expected: PASS.

### Task 4: Map browser-unavailable results and revise runbook claims

**Files:**
- Modify: `backend/app/interfaces/http/interactive_browser.py`
- Modify: `backend/tests/test_api_interactive_browser.py`
- Modify: `docs/interactive-browser-verification.md`

- [ ] **Step 1: Write failing unavailable API test**

```python
def test_continue_returns_conflict_when_browser_handle_is_unavailable(client, owner_headers):
    response = client.post('/api/interactive-browser/sessions/session-1/continue', headers=owner_headers)
    assert response.status_code == 409
```

- [ ] **Step 2: Run it and verify the current route reports 500**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest -q tests/test_api_interactive_browser.py::test_continue_returns_conflict_when_browser_handle_is_unavailable`

Expected: FAIL with status 500.

- [ ] **Step 3: Implement safe mapping and accurate operational documentation**

Catch `InteractiveBrowserUnavailableError` in continue/relay paths and return 409 without process or path details. Update the runbook to state that relay uses a one-time bearer ticket minted by owner-authorised REST (not an independently authenticated WebSocket), reverse proxies must suppress relay query-string logging, manual browser navigation is not itself an arbitrary API, and only browser-context source-rule requests are origin-restricted. Do not claim expired cleanup/publishing behaviour until verified by these tests.

- [ ] **Step 4: Run API and documentation checks**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest -q tests/test_api_interactive_browser.py`

Expected: PASS.

### Task 5: Run full focused verification

**Files:**
- Modify: `frontend/tsconfig.tsbuildinfo` only as generated state, then restore it.

- [ ] **Step 1: Run backend lifecycle and source audit suites**

Run: `/tmp/legado-hub-pytest-venv/bin/pytest -q tests/test_interactive_browser_service.py tests/test_interactive_browser_supervisor.py tests/test_interactive_browser_repo.py tests/test_interactive_browser_factory.py tests/test_api_interactive_browser.py tests/test_source_build_audit_service.py tests/test_source_build_audit_scheduler.py tests/test_source_probe_service.py tests/test_source_build_runtime_service.py tests/test_source_build_ai_repair_service.py tests/test_api_system_settings.py tests/test_source_runtime_repo.py`

Expected: PASS.

- [ ] **Step 2: Run frontend checks and restore generated state**

Run: `node node_modules/vitest/vitest.mjs --run src/features/operations/ManualVerificationPanel.test.tsx src/features/operations/SourceBuildsPage.test.tsx src/features/system/SystemSettingsPage.test.tsx`

Run: `node node_modules/typescript/bin/tsc -b`

Run: `git restore --source=HEAD -- frontend/tsconfig.tsbuildinfo`

Run: `node node_modules/vite/bin/vite.js build`

Expected: all commands exit 0.

- [ ] **Step 3: Inspect and commit**

Run: `git diff --check`

Run: `git status --short`

Expected: only browser-supervisor implementation, tests, runbook, and intentional system-settings changes.

```bash
git add backend frontend docs
git commit -m "fix: harden interactive browser verification lifecycle"
```

## Plan self-review

- **Spec coverage:** Tasks 1-3 resolve the three critical event-loop/lifecycle routes, task 2 fixes relay-token atomicity, task 4 handles API/doc accuracy, and task 5 retains the prior focused source/UI verification gates.
- **Placeholder scan:** All code steps name concrete files, state constraints, test commands, and expected outcomes.
- **Type consistency:** The supervisor exposes the existing async browser API; its core `InteractiveBrowserService` retains all handles only on its owner loop. `transition_state` is the one CAS contract used by cancellation, expiry, automatic validation, and manual validation.
