# Interactive Browser Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Let an authorised source-build owner complete a necessary access verification inside Hub's web UI, while the system first attempts one bounded standard Chromium validation and never publishes an unverified source.

**Architecture:** Source auditing will preserve verification_required instead of converting it to a generic parse failure. A candidate-only browser-session service will own an isolated Chromium profile, a short-lived Hub-authenticated noVNC relay, and a same-session Legado transport for final validation. Cookies, profiles, raw relay tokens, screenshots, and page HTML never enter persistent storage.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, asyncio subprocesses, Playwright with the installed Chromium executable, Xvfb/x11vnc/websockify, @novnc/novnc, React 18, Vitest, pytest.

---

## File structure

| Path | Responsibility |
| --- | --- |
| backend/app/domain/entities/interactive_browser.py | Session states and persistence-safe value objects. |
| backend/app/domain/repositories/interactive_browser_repo.py | Repository boundary for sessions, relay tokens, and events. |
| backend/app/infrastructure/persistence/sqlite/interactive_browser_repo_impl.py | SQLite owner-scoped reads, token digest consumption, and event writes. |
| backend/app/infrastructure/persistence/sqlite/schema.py | Session/event tables with no cookie or page-content columns. |
| backend/app/application/services/interactive_browser_service.py | Lifecycle, automatic attempt, ownership, expiry, and cleanup. |
| backend/app/infrastructure/browser/playwright_driver.py | Standard-browser-only Chromium process driver. |
| backend/app/infrastructure/browser/browser_http_client.py | Active browser-context adapter to existing HttpResponse. |
| backend/app/interfaces/http/interactive_browser.py | Owner-authorised REST endpoints and restricted WebSocket relay. |
| backend/app/application/services/source_build_audit_service.py | Verification classification, automatic-first decision, manual pause. |
| backend/app/application/services/source_build_runtime_service.py | Candidate payload and Agent evidence status. |
| frontend/src/api/modules/interactiveBrowser.ts | Typed session REST client. |
| frontend/src/features/operations/ManualVerificationPanel.tsx | Direct web UI with noVNC stream and continue/cancel controls. |
| frontend/src/features/operations/SourceBuildsPage.tsx | Verification explanation and owner-only action. |
| frontend/src/features/system/SystemSettingsPage.tsx | Administrator feature limits and defaults. |
| backend/requirements.txt, backend/Dockerfile, frontend/package.json | Explicit deployment/runtime dependencies. |

### Task 1: Preserve verification evidence and stop retrying it as a selector failure

**Files:**
- Modify: backend/app/application/services/source_build_audit_service.py
- Modify: backend/app/application/services/source_build_runtime_service.py
- Modify: backend/tests/test_source_build_audit_service.py
- Modify: backend/tests/test_source_build_runtime_service.py

- [ ] **Step 1: Write the failing audit regression test**

~~~python
@pytest.mark.asyncio
async def test_audit_parks_verification_wall_without_retrying_or_failing_candidate():
    service = SourceBuildAuditService(
        runtime_repo=FakeRuntime(candidate_version()),
        probe_service_factory=lambda: ProbeWithContentBlock("verification_wall"),
        build_service=FailIfRepairSubmitted(),
        review_service=FailIfReviewEnqueued(),
    )

    result = await service.audit("source-version-1")

    assert result["status"] == "awaiting_manual_verification"
    assert result["report"]["reason"] == "verification_required"
    assert result["report"]["stages"]["content"]["block_reason"] == "verification_wall"
~~~

- [ ] **Step 2: Run the regression test and confirm current retry behaviour fails it**

Run: pytest tests/test_source_build_audit_service.py::test_audit_parks_verification_wall_without_retrying_or_failing_candidate -v

Expected: FAIL; the current result is retry_queued or failed with content_failed.

- [ ] **Step 3: Implement the smallest classification branch**

In SourceBuildAuditService._evaluate retain content transport evidence and use this decision:

~~~python
is_verification = content.detail.get("block_reason") == "verification_wall"
reason = "verification_required" if is_verification else "content_failed"
stages["content"]["block_reason"] = content.detail.get("block_reason")
~~~

Before _queue_repair_after_pending, persist source_audit status awaiting_manual_verification, record the normal source_test_run, and return without queueing a repair, review, or final source-version failure. Keep the source version in candidate status.

- [ ] **Step 4: Add the runtime-payload regression test**

~~~python
def test_runtime_records_verification_required_without_claiming_agent_validation(tmp_path, monkeypatch):
    result = service.handle_job(job_with_verification_probe())
    payload = repo.get_version(result["source_version_id"]).payload

    assert payload["autonomous_build"]["verification"]["state"] == "verification_required"
    assert payload["autonomous_build"]["agent"]["reason"] != "validated"
~~~

- [ ] **Step 5: Run focused tests**

Run: pytest tests/test_source_build_audit_service.py tests/test_source_build_runtime_service.py -q

Expected: PASS.

- [ ] **Step 6: Commit**

~~~bash
git add backend/app/application/services/source_build_audit_service.py backend/app/application/services/source_build_runtime_service.py backend/tests/test_source_build_audit_service.py backend/tests/test_source_build_runtime_service.py
git commit -m "fix: preserve source verification requirements"
~~~

### Task 2: Persist verification sessions and administrator settings safely

**Files:**
- Create: backend/app/domain/entities/interactive_browser.py
- Create: backend/app/domain/repositories/interactive_browser_repo.py
- Create: backend/app/infrastructure/persistence/sqlite/interactive_browser_repo_impl.py
- Modify: backend/app/infrastructure/persistence/sqlite/schema.py
- Modify: backend/app/domain/repositories/system_settings_repo.py
- Modify: backend/app/infrastructure/persistence/sqlite/system_settings_repo_impl.py
- Modify: backend/app/application/services/system_settings_service.py
- Modify: backend/app/infrastructure/persistence/factory.py
- Modify: backend/app/interfaces/http/system.py
- Create: backend/tests/test_interactive_browser_repo.py
- Modify: backend/tests/test_api_system_settings.py

- [ ] **Step 1: Write failing repository tests**

~~~python
def test_session_repo_is_owner_scoped_and_token_is_single_use(db):
    repo = SQLiteInteractiveBrowserRepository(db)
    session = repo.create(InteractiveBrowserSession.new(
        source_version_id="sv-1", owner_id="42", allowed_origins=["https://books.test"],
    ))
    repo.issue_relay_token(session.id, "42", raw_token="one-time")

    assert repo.get_for_owner(session.id, "42").id == session.id
    assert repo.get_for_owner(session.id, "99") is None
    assert repo.consume_relay_token("one-time", "42").session_id == session.id
    assert repo.consume_relay_token("one-time", "42") is None
    assert "cookie" not in InteractiveBrowserSessionModel.__table__.columns.keys()
~~~

- [ ] **Step 2: Run the test and verify missing types/tables**

Run: pytest tests/test_interactive_browser_repo.py -v

Expected: FAIL with import or table errors.

- [ ] **Step 3: Implement stateful entities and SQLite persistence**

Define exactly these session states:

~~~python
class InteractiveBrowserState(StrEnum):
    PENDING = "pending"
    AUTOMATIC_RUNNING = "automatic_running"
    AWAITING_MANUAL = "awaiting_manual_verification"
    VALIDATING = "validating"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"
~~~

Add interactive_browser_sessions with id, source_version_id, owner_id, allowed_origins JSON, state, automatic_attempted, expires_at, closed_at, terminal_reason, created_at. Add interactive_browser_events with session_id, event_type, actor_id, detail JSON, created_at. Relay tokens are SHA-256 digests plus expiry and consumed_at; raw tokens are never stored. Do not add cookie, storage, HTML, screenshot, or credentials columns.

Extend SystemSettingsRepository with get_int and set_int. Add disabled-by-default settings interactive_browser_verification_enabled and automatic-enabled settings with clamped defaults:

~~~python
{
    "enabled": False,
    "automatic_enabled": True,
    "max_sessions": 1,
    "session_timeout_seconds": 300,
}
~~~

Clamp max_sessions to 1..3 and timeout to 60..600 seconds.

- [ ] **Step 4: Add administrator-only settings API coverage**

Add an InteractiveBrowserSettingsRequest to the existing system router and GET/PUT endpoints at /interactive-browser-settings. Protect both with Permission.SYSTEM_SETTINGS_MANAGE.

~~~python
class InteractiveBrowserSettingsRequest(BaseModel):
    enabled: bool
    automatic_enabled: bool = True
    max_sessions: int = Field(default=1, ge=1, le=3)
    session_timeout_seconds: int = Field(default=300, ge=60, le=600)
~~~

- [ ] **Step 5: Run repository and settings tests**

Run: pytest tests/test_interactive_browser_repo.py tests/test_api_system_settings.py -q

Expected: PASS.

- [ ] **Step 6: Commit**

~~~bash
git add backend/app/domain/entities/interactive_browser.py backend/app/domain/repositories/interactive_browser_repo.py backend/app/infrastructure/persistence/sqlite/interactive_browser_repo_impl.py backend/app/infrastructure/persistence/sqlite/schema.py backend/app/domain/repositories/system_settings_repo.py backend/app/infrastructure/persistence/sqlite/system_settings_repo_impl.py backend/app/application/services/system_settings_service.py backend/app/infrastructure/persistence/factory.py backend/app/interfaces/http/system.py backend/tests/test_interactive_browser_repo.py backend/tests/test_api_system_settings.py
git commit -m "feat: persist interactive browser verification sessions"
~~~

### Task 3: Add a bounded standard-browser supervisor and automatic attempt

**Files:**
- Create: backend/app/application/services/interactive_browser_service.py
- Create: backend/app/infrastructure/browser/playwright_driver.py
- Modify: backend/app/core/config.py
- Modify: backend/app/infrastructure/persistence/factory.py
- Modify: backend/requirements.txt
- Modify: backend/Dockerfile
- Create: backend/tests/test_interactive_browser_service.py
- Create: backend/tests/test_playwright_driver.py

- [ ] **Step 1: Write failing lifecycle tests with a recording driver**

~~~python
@pytest.mark.asyncio
async def test_automatic_attempt_uses_one_standard_browser_then_waits_for_manual():
    driver = RecordingBrowserDriver(result=BrowserAttemptResult.needs_manual("verification_required"))
    service = InteractiveBrowserService(repo=FakeSessionRepo(), driver=driver, settings=EnabledSettings())

    session = await service.start_or_resume(
        source_version_id="sv-1", owner_id="42", allowed_origins=["https://books.test"],
    )

    assert driver.start_calls == 1
    assert session.state == InteractiveBrowserState.AWAITING_MANUAL
    assert session.automatic_attempted is True
    assert driver.options == {"headless": False, "proxy": None, "stealth": False}
~~~

- [ ] **Step 2: Run the lifecycle tests**

Run: pytest tests/test_interactive_browser_service.py tests/test_playwright_driver.py -v

Expected: FAIL because the supervisor and driver do not exist.

- [ ] **Step 3: Implement the narrow driver protocol**

~~~python
class BrowserSessionDriver(Protocol):
    async def start(self, *, profile_dir: Path, initial_url: str, allowed_origins: set[str]) -> BrowserHandle:
        raise NotImplementedError

    async def automatic_probe(self, handle: BrowserHandle) -> BrowserAttemptResult:
        raise NotImplementedError

    async def snapshot(self, handle: BrowserHandle) -> SanitizedPageSnapshot:
        raise NotImplementedError

    async def close(self, handle: BrowserHandle) -> None:
        raise NotImplementedError
~~~

InteractiveBrowserService must enforce owner, expiry, one automatic attempt, configured concurrency, and try/finally cleanup. It keeps process handles in memory only; after a process restart recover_expired_sessions marks every non-terminal record expired and removes its profile.

PlaywrightBrowserDriver must use an explicit configured Chromium executable and a new profile directory below INTERACTIVE_BROWSER_PROFILE_ROOT. It starts Xvfb, Chromium, x11vnc, and websockify using argv arrays and loopback bind addresses. It must not offer proxy, custom header, cookie export, extension, arbitrary evaluation, stealth, fingerprint, or CAPTCHA-solving features.

- [ ] **Step 4: Make missing-runtime status explicit**

Return browser_unavailable if Chromium, Xvfb, x11vnc, websockify, or the writable profile root is unavailable. Do not build an unquoted shell command, and do not fall back to a public port.

- [ ] **Step 5: Add dependencies and container packages**

Add playwright==1.52.0 and websockets==15.0.1 to backend/requirements.txt. Install chromium, xvfb, x11vnc, and websockify in the Dockerfile. Configure the installed Chromium path; do not run playwright install or download a browser binary.

- [ ] **Step 6: Verify tests**

Run: pytest tests/test_interactive_browser_service.py tests/test_playwright_driver.py -q

Expected: PASS with a fake subprocess runner; tests must never launch a real browser.

- [ ] **Step 7: Commit**

~~~bash
git add backend/app/application/services/interactive_browser_service.py backend/app/infrastructure/browser/playwright_driver.py backend/app/core/config.py backend/app/infrastructure/persistence/factory.py backend/requirements.txt backend/Dockerfile backend/tests/test_interactive_browser_service.py backend/tests/test_playwright_driver.py
git commit -m "feat: add bounded interactive browser supervisor"
~~~

### Task 4: Validate rules through the active browser context, not copied cookies

**Files:**
- Create: backend/app/infrastructure/browser/browser_http_client.py
- Modify: backend/app/infrastructure/legado/legado_fetcher.py
- Modify: backend/app/application/services/source_probe_service.py
- Modify: backend/app/application/services/interactive_browser_service.py
- Create: backend/tests/test_browser_http_client.py
- Modify: backend/tests/test_source_probe_service.py

- [ ] **Step 1: Write the failing adapter test**

~~~python
@pytest.mark.asyncio
async def test_browser_http_client_returns_existing_http_response_shape_and_blocks_other_origins():
    page = FakeBrowserPage(url="https://books.test/chapter/1", html="<article>" + "x" * 100 + "</article>")
    client = BrowserHttpClient(page=page, allowed_origins={"https://books.test"})

    response = await client.get("https://books.test/chapter/1")
    blocked = await client.get("https://other.test/")

    assert response.success is True
    assert response.is_html is True
    assert response.text.startswith("<article>")
    assert blocked.error == "cross_origin"
~~~

- [ ] **Step 2: Run the adapter test**

Run: pytest tests/test_browser_http_client.py -v

Expected: FAIL with module-not-found.

- [ ] **Step 3: Inject the existing HTTP interface into the Legado fetcher**

~~~python
def __init__(self, timeout=15, max_retries=2, verify_ssl=False, max_concurrent=10, http_client=None):
    self._http = http_client or LegadoHttpClient(
        timeout=timeout,
        max_retries=max_retries,
        verify_ssl=verify_ssl,
        max_concurrent=max_concurrent,
    )
~~~

BrowserHttpClient implements only the current asynchronous get, post, and close surface and returns the existing HttpResponse type. It navigates/fetches only inside allowed_origins in the active Playwright context and never serializes browser storage. Form and JSON POST requests are restricted to source-rule validation needs.

- [ ] **Step 4: Add a browser-backed probe factory**

InteractiveBrowserService creates SourceProbeService(LegadoBookSourceFetcher(http_client=BrowserHttpClient(page=handle.page, allowed_origins=handle.allowed_origins))) for the active session. Both automatic success and manual Continue validation must require a full search/TOC/content probe. A readable browser page by itself is not a publish signal.

- [ ] **Step 5: Verify parser and adapter tests**

Run: pytest tests/test_browser_http_client.py tests/test_source_probe_service.py -q

Expected: PASS.

- [ ] **Step 6: Commit**

~~~bash
git add backend/app/infrastructure/browser/browser_http_client.py backend/app/infrastructure/legado/legado_fetcher.py backend/app/application/services/source_probe_service.py backend/app/application/services/interactive_browser_service.py backend/tests/test_browser_http_client.py backend/tests/test_source_probe_service.py
git commit -m "feat: validate source rules in browser sessions"
~~~

### Task 5: Wire automatic-first/manual-pause workflow into audit and Agent evidence

**Files:**
- Modify: backend/app/application/services/source_build_audit_service.py
- Modify: backend/app/application/services/source_build_runtime_service.py
- Modify: backend/app/application/services/source_build_ai_repair_service.py
- Modify: backend/app/infrastructure/persistence/factory.py
- Modify: backend/tests/test_source_build_audit_service.py
- Modify: backend/tests/test_source_build_runtime_service.py
- Modify: backend/tests/test_source_build_ai_repair_service.py

- [ ] **Step 1: Write a failing automatic-first integration test**

~~~python
@pytest.mark.asyncio
async def test_verification_wall_runs_one_automatic_browser_validation_then_parks_for_manual():
    browsers = FakeInteractiveBrowserService(automatic_result="needs_manual")
    build_service = FailIfRepairSubmitted()
    audit = SourceBuildAuditService(
        runtime_repo=FakeRuntime(candidate_version()),
        probe_service_factory=lambda: ProbeWithContentBlock("verification_wall"),
        build_service=build_service,
        review_service=FailIfReviewEnqueued(),
        interactive_browser_service=browsers,
    )

    result = await audit.audit("sv-1")

    assert browsers.automatic_calls == ["sv-1"]
    assert result["status"] == "awaiting_manual_verification"
    assert result["report"]["reason"] == "verification_required"
    assert build_service.audit_repair_submissions == []
~~~

- [ ] **Step 2: Run the integration test**

Run: pytest tests/test_source_build_audit_service.py::test_verification_wall_runs_one_automatic_browser_validation_then_parks_for_manual -v

Expected: FAIL because the audit service lacks the browser collaborator.

- [ ] **Step 3: Integrate through an explicit result contract**

Add an optional interactive_browser_service constructor dependency. On verification_required it calls:

~~~python
browser_result = await self._interactive_browser.attempt_automatic(
    source_version_id=version.id,
    owner_id=version.created_by,
    source_rule=source_rule,
    keyword=keyword,
)
~~~

A passing browser full-chain report follows existing candidate/review rules. A needs_manual report persists session id and awaiting_manual_verification. A disabled/unavailable result persists verification_required plus manual_available false. None of these states requeue Agent repairs for the same access-verification event.

Record a browser.inspect tool result with only classification, session id, and pass booleans. SourceBuildAIRepairService may receive bounded snapshot/probe evidence but no browser handle, control tool, cookie, or relay URL.

- [ ] **Step 4: Run focused workflow tests**

Run: pytest tests/test_source_build_audit_service.py tests/test_source_build_runtime_service.py tests/test_source_build_ai_repair_service.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add backend/app/application/services/source_build_audit_service.py backend/app/application/services/source_build_runtime_service.py backend/app/application/services/source_build_ai_repair_service.py backend/app/infrastructure/persistence/factory.py backend/tests/test_source_build_audit_service.py backend/tests/test_source_build_runtime_service.py backend/tests/test_source_build_ai_repair_service.py
git commit -m "feat: add automatic browser verification workflow"
~~~

### Task 6: Expose owner-scoped session controls and a restricted relay

**Files:**
- Create: backend/app/interfaces/http/interactive_browser.py
- Modify: backend/app/interfaces/http/router.py
- Modify: backend/app/core/permissions.py
- Modify: backend/app/infrastructure/persistence/factory.py
- Create: backend/tests/test_api_interactive_browser.py

- [ ] **Step 1: Write failing ownership and cleanup API tests**

~~~python
def test_owner_can_open_continue_and_cancel_own_session(client, owner_headers):
    opened = client.post("/api/interactive-browser/sessions", json={"source_version_id": "sv-1"}, headers=owner_headers)
    assert opened.status_code == 200
    session_id = opened.json()["data"]["id"]

    assert client.post(f"/api/interactive-browser/sessions/{session_id}/continue", headers=owner_headers).status_code == 200
    assert client.delete(f"/api/interactive-browser/sessions/{session_id}", headers=owner_headers).status_code == 200


def test_other_user_cannot_access_or_relay_owners_session(client, owner_headers, other_headers):
    session_id = client.post("/api/interactive-browser/sessions", json={"source_version_id": "sv-1"}, headers=owner_headers).json()["data"]["id"]

    assert client.get(f"/api/interactive-browser/sessions/{session_id}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/interactive-browser/sessions/{session_id}", headers=other_headers).status_code == 404
~~~

- [ ] **Step 2: Run the API tests**

Run: pytest tests/test_api_interactive_browser.py -v

Expected: FAIL with 404 because the router is absent.

- [ ] **Step 3: Add narrow routes and authorization**

Create this exact surface:

~~~text
POST   /api/interactive-browser/sessions
GET    /api/interactive-browser/sessions/{session_id}
POST   /api/interactive-browser/sessions/{session_id}/continue
DELETE /api/interactive-browser/sessions/{session_id}
WS     /api/interactive-browser/sessions/{session_id}/relay?token=relay_token
~~~

Use get_current_identity, require Permission.ENGINE_TEST, and verify source-version ownership against console:{identity.user_id}. Do not equate list/read permissions with browser control.

POST returns a one-time relay URL after explicit host confirmation. The WebSocket verifies token digest, token expiry, owner, Origin header, and active state before byte-relaying only to the matching loopback websockify port. It consumes/revokes the token on disconnect and cannot proxy arbitrary hosts, paths, or ports.

- [ ] **Step 4: Implement terminal actions**

Continue is valid only from awaiting_manual_verification; it triggers browser-backed full-chain validation and finally closes the session. Delete revokes tokens, kills process groups, removes the profile, writes an event, and returns cancelled. Every error path has the same cleanup guarantee.

- [ ] **Step 5: Run API tests**

Run: pytest tests/test_api_interactive_browser.py -q

Expected: PASS.

- [ ] **Step 6: Commit**

~~~bash
git add backend/app/interfaces/http/interactive_browser.py backend/app/interfaces/http/router.py backend/app/core/permissions.py backend/app/infrastructure/persistence/factory.py backend/tests/test_api_interactive_browser.py
git commit -m "feat: expose owner-scoped verification sessions"
~~~

### Task 7: Build the direct Hub web panel and system controls

**Files:**
- Create: frontend/src/api/modules/interactiveBrowser.ts
- Create: frontend/src/features/operations/ManualVerificationPanel.tsx
- Create: frontend/src/features/operations/ManualVerificationPanel.test.tsx
- Modify: frontend/src/api/modules/operations.ts
- Modify: frontend/src/features/operations/SourceBuildsPage.tsx
- Modify: frontend/src/features/operations/SourceBuildsPage.test.tsx
- Modify: frontend/src/api/modules/system.ts
- Modify: frontend/src/features/system/SystemSettingsPage.tsx
- Modify: frontend/src/features/system/SystemSettingsPage.test.tsx
- Modify: frontend/package.json

- [ ] **Step 1: Write the failing manual panel test**

~~~tsx
test("renders target host and waits for explicit continue", async () => {
  interactiveBrowserMocks.createSession.mockResolvedValueOnce(envelope({
    id: "browser-1",
    state: "awaiting_manual_verification",
    targetHost: "books.test",
    expiresAt: "2026-07-15T12:05:00Z",
    relayUrl: "wss://hub.test/api/interactive-browser/sessions/browser-1/relay?token=once",
  }))

  render(<ManualVerificationPanel sourceVersionId="sv-1" onFinished={vi.fn()} />)

  expect(await screen.findByText("books.test")).toBeInTheDocument()
  expect(screen.getByRole("button", {name: "Continue validation"})).toBeInTheDocument()
})
~~~

- [ ] **Step 2: Run the panel test**

Run: node node_modules/vitest/vitest.mjs --run src/features/operations/ManualVerificationPanel.test.tsx

Expected: FAIL with module-not-found.

- [ ] **Step 3: Implement typed API and noVNC panel**

Add @novnc/novnc. Instantiate RFB only after the owner-scoped create-session response returns a relay URL. Show target host, expiry countdown, automatic attempt result, Continue validation, and Cancel/destroy session. Destroy the RFB object on cleanup; call cancel only on explicit user cancellation, not an incidental development-mode React unmount.

In SourceBuildsPage render verification_required as 需要人工验证 with the returned reason. Render the action only when manual_verification_allowed is provided by the server; do not infer ownership client-side.

- [ ] **Step 4: Write the failing settings UI test**

~~~tsx
test("saves disabled-by-default interactive browser verification settings", async () => {
  render(<SystemSettingsPage />)

  const control = await screen.findByRole("switch", {name: "Interactive browser verification"})
  expect(control).not.toBeChecked()

  fireEvent.click(control)
  expect(systemMocks.updateInteractiveBrowserSettings).toHaveBeenCalledWith({
    enabled: true,
    automaticEnabled: true,
    maxSessions: 1,
    sessionTimeoutSeconds: 300,
  })
})
~~~

- [ ] **Step 5: Implement settings controls and run UI tests**

Follow the existing SystemSettingsPage loading, saving, and error conventions. Keep automatic enabled only when the parent toggle is enabled. Clamp numeric input in both client and server and surface runtime-unavailable messages without exposing file paths, ports, or process arguments.

Run: node node_modules/vitest/vitest.mjs --run src/features/operations/ManualVerificationPanel.test.tsx src/features/operations/SourceBuildsPage.test.tsx src/features/system/SystemSettingsPage.test.tsx

Expected: PASS.

- [ ] **Step 6: Commit**

~~~bash
git add frontend/package.json frontend/src/api/modules/interactiveBrowser.ts frontend/src/api/modules/operations.ts frontend/src/api/modules/system.ts frontend/src/features/operations/ManualVerificationPanel.tsx frontend/src/features/operations/ManualVerificationPanel.test.tsx frontend/src/features/operations/SourceBuildsPage.tsx frontend/src/features/operations/SourceBuildsPage.test.tsx frontend/src/features/system/SystemSettingsPage.tsx frontend/src/features/system/SystemSettingsPage.test.tsx
git commit -m "feat: add web-based manual verification panel"
~~~

### Task 8: Verify deployment boundaries, regression coverage, and authorised flow

**Files:**
- Create: docs/interactive-browser-verification.md
- Modify: docs/superpowers/specs/2026-07-15-interactive-browser-verification-design.md only if implementation decisions change the approved design.

- [ ] **Step 1: Write the runtime runbook**

Document the disabled-by-default switch, local Chromium/Xvfb/x11vnc/websockify requirements, loopback-only listeners, ownership/authorization requirement, capability-unavailable state, expiry, and cleanup procedure. Do not document CAPTCHA solving, proxies, stealth, fingerprint manipulation, or cookie extraction.

- [ ] **Step 2: Run backend boundary suite**

Run: pytest tests/test_source_probe_service.py tests/test_source_build_audit_service.py tests/test_source_build_runtime_service.py tests/test_source_build_ai_repair_service.py tests/test_interactive_browser_repo.py tests/test_interactive_browser_service.py tests/test_browser_http_client.py tests/test_api_interactive_browser.py tests/test_api_system_settings.py -q

Expected: PASS.

- [ ] **Step 3: Run frontend tests and builds**

Run: node node_modules/vitest/vitest.mjs --run src/features/operations/ManualVerificationPanel.test.tsx src/features/operations/SourceBuildsPage.test.tsx src/features/system/SystemSettingsPage.test.tsx

Expected: PASS.

Run: node node_modules/typescript/bin/tsc -b

Expected: exit code 0.

Run: node node_modules/vite/bin/vite.js build

Expected: production build succeeds.

- [ ] **Step 4: Perform manual smoke test only against an owned or explicitly authorised endpoint**

1. Enable the feature in System Settings.
2. Submit a controlled source that reports verification_wall to ordinary HTTP but succeeds in a normal browser context.
3. Verify one automatic attempt occurs.
4. If interaction is required, verify the Hub panel shows only target host and that Cancel/expiry remove the session.
5. Complete the authorised interaction, click Continue validation, and confirm only full search/TOC/content success enters the existing candidate/review path.
6. Inspect SQLite session/event rows and confirm no cookie, page HTML, screenshot, raw relay token, or credential was persisted.

- [ ] **Step 5: Restore generated TypeScript state, commit docs, and inspect worktree**

Run: git restore --source=HEAD -- frontend/tsconfig.tsbuildinfo

Run: git status --short

Expected: only selected runbook/design files.

~~~bash
git add docs/interactive-browser-verification.md docs/superpowers/specs/2026-07-15-interactive-browser-verification-design.md
git commit -m "docs: document interactive browser verification"
~~~

## Plan self-review

- **Spec coverage:** Task 1 implements verification classification. Tasks 2-3 establish disabled-by-default, bounded browser ownership and cleanup. Task 4 makes final validation use the same browser context rather than copied cookies. Task 5 makes the path automatic-first and keeps Agent evidence read-only. Task 6 protects the relay. Task 7 gives the requested direct web experience. Task 8 verifies full-chain publication, cleanup, and deployment boundaries.
- **Placeholder scan:** Every task names concrete production/test files, test names, states, interfaces, commands, expected results, and commits.
- **Type consistency:** verification_required is the probe/audit reason; awaiting_manual_verification is the session/audit state. The BrowserHandle stays between service and driver. The Agent receives only SanitizedPageSnapshot/probe evidence, never a handle, browser state, cookie, or relay token.
