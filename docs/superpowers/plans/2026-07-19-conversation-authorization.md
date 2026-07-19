# Conversation Tool Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Add Hermes/OpenClaw-style, auditable authorization cards that pause an AI conversation before \`source.search\`, \`toc.get\`, or \`chapter.fetch\`, then resume the exact model/tool loop after the user chooses a scope.

**Architecture:** Keep \`book_sources.read\` as the immutable RBAC upper bound. Add durable authorization-request and grant repositories, a small application service for atomic decisions, and a continuation-aware gate inside \`AIWorkspaceService\`. Expose idempotent decision/revoke HTTP endpoints and render the returned authorization state in the existing AI workspace without trusting client-supplied tool names or scopes.

**Tech Stack:** FastAPI/Pydantic, Python dataclasses, SQLAlchemy SQLite bootstrap, existing AI workspace/provider/tool executor, React 18 + TypeScript + Vitest/Testing Library, existing audit repository and i18n catalog.

---

## Task 0: Isolate and baseline the existing anti-loop fix

**Files:**
- Modify only the already changed files: \`backend/app/application/services/ai_workspace_service.py\`, \`backend/app/interfaces/http/ai.py\`, \`backend/tests/test_ai_workspace_service.py\`, \`backend/tests/test_ai_workspace_tool_permissions.py\`.
- Do not stage unrelated dirty files in the worktree.

- [ ] **Step 1: Run the current regression slice.**

Run from \`/tmp/legado-hub-release\`:

```bash
../legado-hub-pytest-venv/bin/python -m pytest \
  backend/tests/test_ai_workspace_tool_permissions.py \
  backend/tests/test_ai_workspace_service.py \
  backend/tests/test_novel_analysis_tool_executor.py \
  backend/tests/test_openai_compatible_provider.py -q
```

Expected: \`33 passed\` (or the same tests with any newly added baseline count).

- [ ] **Step 2: Commit only the baseline fix.**

```bash
git add backend/app/application/services/ai_workspace_service.py \
  backend/app/interfaces/http/ai.py \
  backend/tests/test_ai_workspace_service.py \
  backend/tests/test_ai_workspace_tool_permissions.py
git commit -m "fix: stop repeated ai source tool calls"
```

This keeps the authorization feature reviewable and prevents unrelated local changes from entering the feature commits.

## Task 1: Add durable authorization entities, schema, and repositories

**Files:**
- Create: \`backend/app/domain/entities/ai_authorization.py\`
- Create: \`backend/app/domain/repositories/ai_authorization_repo.py\`
- Create: \`backend/app/infrastructure/persistence/sqlite/ai_authorization_repo_impl.py\`
- Modify: \`backend/app/domain/entities/ai_conversation.py\`
- Modify: \`backend/app/infrastructure/persistence/sqlite/schema.py\`
- Modify: \`backend/app/infrastructure/persistence/sqlite/ai_conversation_repo_impl.py\`
- Modify: \`backend/app/infrastructure/persistence/sqlite/bootstrap.py\`
- Modify: \`backend/app/infrastructure/persistence/factory.py\`
- Test: \`backend/tests/test_ai_authorization_repo.py\`
- Test: \`backend/tests/test_ai_conversation_repo.py\`

- [ ] **Step 1: Write failing entity/repository tests.**

Cover creation and retrieval by actor/conversation, one active request per conversation, atomic pending claim, grant expiry/revocation, and message metadata round-tripping:

```python
def test_claim_pending_authorization_is_atomic(tmp_path, monkeypatch):
    repo = make_authorization_repo(tmp_path, monkeypatch)
    request = repo.create_request(make_pending_request())
    first = repo.claim_pending(request.id, actor_id="7", conversation_id="c1")
    second = repo.claim_pending(request.id, actor_id="7", conversation_id="c1")
    assert first.status == "approved_claimed"
    assert second is None
```

```python
def test_conversation_message_metadata_survives_sqlite_round_trip(tmp_path, monkeypatch):
    repo = make_conversation_repo(tmp_path, monkeypatch)
    saved = repo.append_message(AIConversationMessage(
        id="m1", conversation_id="c1", role="assistant", mode="chat",
        content="需要授权", status="authorization_required",
        metadata={"authorization_request_id": "auth-1"},
    ))
    assert saved.metadata["authorization_request_id"] == "auth-1"
```

- [ ] **Step 2: Run the tests and verify they fail.**

```bash
../legado-hub-pytest-venv/bin/python -m pytest \
  backend/tests/test_ai_authorization_repo.py \
  backend/tests/test_ai_conversation_repo.py -q
```

Expected: collection or assertion failures because the entities, tables, metadata column, and repository methods do not exist.

- [ ] **Step 3: Implement the domain contracts.**

Define \`AIConversationAuthorizationRequest\` with \`id\`, \`actor_id\`, \`conversation_id\`, \`message_id\`, \`requested_tools\`, \`requested_calls\`, \`purpose\`, \`continuation\`, \`status\`, \`decision\`, \`expires_at\`, \`resolved_at\`, \`resolved_by\`, \`result_message_id\`, and timestamps. Define \`AIConversationAuthorizationGrant\` with \`id\`, \`actor_id\`, optional \`conversation_id\`, \`scope\`, \`tool_names\`, \`expires_at\`, \`revoked_at\`, and timestamps. Keep statuses and scopes as validated strings so SQLite and API layers share one vocabulary.

Add \`metadata: dict = field(default_factory=dict)\` to \`AIConversationMessage\` and persist it as \`metadata_payload\` with a JSON default. Add SQLAlchemy models and indexes for actor, conversation, status, expiry, and grant scope. Implement repository methods with actor/conversation filters and a conditional SQL update for the pending claim; never return another actor's request or grant.

Update \`bootstrap_sqlite()\` to create the new tables and add \`metadata_payload\` to existing \`ai_conversation_messages\` when absent. Wire \`build_ai_authorization_repository()\` through the persistence factory.

- [ ] **Step 4: Run the repository tests and the existing conversation tests.**

```bash
../legado-hub-pytest-venv/bin/python -m pytest \
  backend/tests/test_ai_authorization_repo.py \
  backend/tests/test_ai_conversation_repo.py -q
```

Expected: PASS, including a fresh temporary SQLite database and a database that existed before the new column.

- [ ] **Step 5: Commit the persistence slice.**

```bash
git add backend/app/domain/entities/ai_authorization.py \
  backend/app/domain/repositories/ai_authorization_repo.py \
  backend/app/infrastructure/persistence/sqlite/ai_authorization_repo_impl.py \
  backend/app/domain/entities/ai_conversation.py \
  backend/app/infrastructure/persistence/sqlite/schema.py \
  backend/app/infrastructure/persistence/sqlite/ai_conversation_repo_impl.py \
  backend/app/infrastructure/persistence/sqlite/bootstrap.py \
  backend/app/infrastructure/persistence/factory.py \
  backend/tests/test_ai_authorization_repo.py backend/tests/test_ai_conversation_repo.py
git commit -m "feat: persist ai conversation authorization state"
```

## Task 2: Implement the authorization application service

**Files:**
- Create: \`backend/app/application/services/ai_authorization_service.py\`
- Modify: \`backend/app/infrastructure/persistence/factory.py\`
- Test: \`backend/tests/test_ai_authorization_service.py\`

- [ ] **Step 1: Write failing service tests.**

Test \`create_request()\` produces a fixed purpose from the mode/tool set, rejects tools outside \`source.search\`, \`toc.get\`, and \`chapter.fetch\`, clamps TTLs to 15 minutes/24 hours/30 days, and redacts sensitive keys. Test \`decide()\` for \`once\`, \`conversation\`, \`remember\`, and \`deny\`; repeat decisions must return the stored result instead of executing again. Test actor/conversation mismatch, expiry, and revocation.

```python
async def test_decision_is_idempotent_and_creates_only_one_grant():
    service, repo = make_authorization_service()
    request = await service.create_request(make_request())
    first = await service.decide(request.id, actor_id="7", conversation_id="c1", decision="conversation")
    second = await service.decide(request.id, actor_id="7", conversation_id="c1", decision="conversation")
    assert first["status"] == second["status"] == "approved_conversation"
    assert repo.count_active_grants(actor_id="7", conversation_id="c1") == 1
```

- [ ] **Step 2: Run the service tests and verify failure.**

```bash
../legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_ai_authorization_service.py -q
```

Expected: FAIL because the service and grant policy do not exist.

- [ ] **Step 3: Implement the service with fixed policy boundaries.**

Expose these methods with the following concrete contracts: `create_request(actor_id, conversation_id, message_id, mode, requested_tools, requested_calls, continuation) -> dict`, `decide(request_id, actor_id, conversation_id, decision) -> dict`, `list_pending(actor_id, conversation_id) -> list[dict]`, `list_grants(actor_id, conversation_id=None) -> list[dict]`, `revoke_grant(grant_id, actor_id) -> dict`, and `active_tool_names(actor_id, conversation_id, rbac_permissions) -> set[str]`.

Generate purposes from \`MODE_PROMPTS\`/a fixed map, sanitize continuation payloads with the existing boundary redaction helper, and enforce a bounded JSON size. \`decide()\` must claim the request before creating a grant, use the repository's conditional transition, audit every decision, and return the existing result when the request is already resolved. \`active_tool_names()\` must re-check \`book_sources.read\` through the caller-provided RBAC set; a stored grant alone is never sufficient.

- [ ] **Step 4: Run service and repository tests.**

```bash
../legado-hub-pytest-venv/bin/python -m pytest \
  backend/tests/test_ai_authorization_repo.py \
  backend/tests/test_ai_authorization_service.py -q
```

Expected: PASS with no sensitive value in serialized request or audit detail.

- [ ] **Step 5: Commit the policy service.**

```bash
git add backend/app/application/services/ai_authorization_service.py \
  backend/app/infrastructure/persistence/factory.py \
  backend/tests/test_ai_authorization_service.py
git commit -m "feat: add conversation authorization policy service"
```

## Task 3: Gate and resume the AI workspace tool loop

**Files:**
- Modify: \`backend/app/application/services/ai_workspace_service.py\`
- Modify: \`backend/app/infrastructure/persistence/factory.py\`
- Test: \`backend/tests/test_ai_workspace_authorization.py\`
- Test: \`backend/tests/test_ai_workspace_service.py\`

- [ ] **Step 1: Add failing workspace tests.**

Use a fake novel executor that records invocations and a fake platform that returns a \`source.search\` call. Verify the first \`send_message()\` returns \`status == "authorization_required"\`, creates no novel-tool invocation, and includes a request ID. Verify approving once resumes the exact saved call, then allows \`toc.get\` and \`chapter.fetch\` within that task. Add cases for explicit client \`tool_requests\`, no RBAC, denied/expired requests, repeated model calls, rejected tools, and a second message while a request is pending.

```python
async def test_model_content_call_pauses_before_execution(tmp_path, monkeypatch):
    service, platform, executor = make_workspace_with_authorization(tmp_path, monkeypatch)
    conversation = await service.create_conversation("7")
    reply = await service.send_message(conversation["id"], "7", "character", "分析主角", allowed_tool_names={"source.search"})
    assert reply["status"] == "authorization_required"
    assert executor.calls == []
    assert reply["authorization_request"]["choices"] == ["once", "conversation", "remember", "deny"]
```

- [ ] **Step 2: Run the new tests and verify failure.**

```bash
../legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_ai_workspace_authorization.py -q
```

Expected: FAIL because the current service executes or rejects content tools without a pending authorization result.

- [ ] **Step 3: Implement the gate and continuation result.**

Introduce an internal \`_ToolLoopResult\` containing \`content\`, \`tool_calls\`, and optional \`authorization_request\`. Compute effective content tools from RBAC plus active grants, but continue exposing RBAC-allowed content schemas so the model can request them. Before \`_execute_model_tool_call\` and before explicit content \`tool_requests\`, call the authorization service; on a missing grant, persist sanitized \`messages\`, \`executed_calls\`, the pending model call, mode, actor, conversation, and evidence requirement, append an assistant message with \`status="authorization_required"\` and metadata, and return without invoking the executor.

Add \`decide_authorization()\` on \`AIWorkspaceService\`. It loads and claims the request through the policy service, restores the continuation, injects only the approved tool subset, executes the pending call, and runs the existing max-turn/fingerprint/rejected safeguards. Store \`result_message_id\` so retries return the same assistant message. \`get_conversation()\` must expose current authorization metadata, and list methods must support pending request hydration.

Keep the existing refusal text when content evidence is unavailable, but distinguish \`authorization_denied\`, \`authorization_expired\`, and \`source_unavailable\` in message metadata. Never make a second model call merely because an authorization decision was denied.

- [ ] **Step 4: Run the focused workspace suite.**

```bash
../legado-hub-pytest-venv/bin/python -m pytest \
  backend/tests/test_ai_workspace_authorization.py \
  backend/tests/test_ai_workspace_service.py \
  backend/tests/test_ai_workspace_tool_permissions.py -q
```

Expected: PASS; executor call counts prove no pre-approval fetch and no duplicate fetch after repeated approval.

- [ ] **Step 5: Commit the workspace gate.**

```bash
git add backend/app/application/services/ai_workspace_service.py \
  backend/app/infrastructure/persistence/factory.py \
  backend/tests/test_ai_workspace_authorization.py \
  backend/tests/test_ai_workspace_service.py
git commit -m "feat: gate ai source reads behind conversation authorization"
```

## Task 4: Expose decision, pending, grant, and revoke HTTP APIs

**Files:**
- Modify: \`backend/app/interfaces/http/ai.py\`
- Create: \`backend/tests/test_api_ai_authorization.py\`

- [ ] **Step 1: Write failing API contract tests.**

Use the existing FastAPI test client and signed access tokens. Cover:

```python
def test_decision_endpoint_returns_resumed_message(client, pending_request, token):
    response = client.post(
        f"/api/ai/conversations/{pending_request.conversation_id}/authorization-requests/{pending_request.id}/decision",
        headers=auth(token), json={"decision": "once"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["authorization"]["status"] == "consumed"
```

Also assert 403 for missing \`ai.run\`, 404 for another user's conversation/request, 422 for an invalid decision, idempotent repeated decisions, pending filtering, and revoke behavior.

- [ ] **Step 2: Run the API tests and verify failure.**

```bash
../legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_api_ai_authorization.py -q
```

Expected: FAIL because the routes and Pydantic decision model are absent.

- [ ] **Step 3: Add the strict FastAPI contracts.**

Add \`AuthorizationDecisionRequest\` with a literal/regex limited to \`once|conversation|remember|deny\`. Add these four routes under the existing AI router: \`POST /conversations/{conversation_id}/authorization-requests/{request_id}/decision\`, \`GET /conversations/{conversation_id}/authorization-requests\`, \`GET /authorization-grants\`, and \`POST /authorization-grants/{grant_id}/revoke\`. Each handler must call the matching workspace/policy service method with the authenticated identity and return \`ok(data=result, message="ai authorization updated")\`; do not use a wildcard route or accept arbitrary JSON keys.

Every handler uses \`require_permission(Permission.AI_RUN)\`, passes the authenticated user ID, and lets the service enforce conversation ownership and the source RBAC upper bound. Return the existing \`ok()\` envelope and stable business codes/messages; never accept tools or purpose from the client.

- [ ] **Step 4: Run API and existing AI route tests.**

```bash
../legado-hub-pytest-venv/bin/python -m pytest \
  backend/tests/test_api_ai_authorization.py \
  backend/tests/test_api_ai_workspace.py \
  backend/tests/test_ai_workspace_tool_permissions.py -q
```

Expected: PASS with the standard \`{success, code, message, data, trace_id}\` envelope.

- [ ] **Step 5: Commit the HTTP layer.**

```bash
git add backend/app/interfaces/http/ai.py backend/tests/test_api_ai_authorization.py
git commit -m "feat: expose ai conversation authorization endpoints"
```

## Task 5: Add frontend API types and authorization card UI

**Files:**
- Modify: \`frontend/src/api/modules/ai.ts\`
- Modify: \`frontend/src/features/ai/AIWorkspacePage.tsx\`
- Modify: \`frontend/src/lib/i18n.ts\`
- Test: \`frontend/src/features/ai/AIWorkspacePage.test.tsx\`

- [ ] **Step 1: Add failing UI tests.**

Extend the existing AI workspace mocks to return an \`authorization_required\` message. Assert the card renders purpose, tool labels, and four choices; clicking “本次” calls the decision API once and renders the resumed assistant message; a pending request reappears after reload; revoke calls the grant API; English locale uses English labels.

```tsx
expect(screen.getByRole('button', { name: '本次允许' })).toBeInTheDocument()
await user.click(screen.getByRole('button', { name: '本次允许' }))
expect(aiMocks.decideAIConversationAuthorization).toHaveBeenCalledWith(
  'conversation-1', 'request-1', { decision: 'once' },
)
```

- [ ] **Step 2: Run the UI test and verify failure.**

```bash
cd frontend && npm test -- --run src/features/ai/AIWorkspacePage.test.tsx
```

Expected: FAIL because the types, API methods, and card do not exist.

- [ ] **Step 3: Implement typed API methods and state.**

Add \`AIConversationMessageStatus\` including \`authorization_required\` and \`denied\`, \`AIConversationAuthorizationRequest\`, \`AIConversationAuthorizationGrant\`, and API methods:

```ts
export function decideAIConversationAuthorization(
  conversationId: string,
  requestId: string,
  payload: { decision: 'once' | 'conversation' | 'remember' | 'deny' },
): Promise<ApiEnvelope<{ authorization: AIConversationAuthorizationRequest; message?: AIConversationMessage }>>

export function listAIConversationAuthorizations(conversationId: string): Promise<ApiEnvelope<AIConversationAuthorizationRequest[]>>
export function listAIAuthorizationGrants(): Promise<ApiEnvelope<AIConversationAuthorizationGrant[]>>
export function revokeAIAuthorizationGrant(grantId: string): Promise<ApiEnvelope<AIConversationAuthorizationGrant>>
```

In \`AIWorkspacePage\`, load pending authorizations with the conversation, render a dedicated card component inside the message list, disable decision buttons while resolving, append the returned message, and show an active conversation grant with a revoke button. Keep optimistic user messages unchanged and make decision requests idempotent by disabling the card until the server responds.

Add all card, status, tool, expiry, revoke, and error strings to both catalogs in \`frontend/src/lib/i18n.ts\`; use the existing \`t()\` path rather than inline language conditionals.

- [ ] **Step 4: Run frontend typecheck, focused tests, and build.**

```bash
cd frontend
npm test -- --run src/features/ai/AIWorkspacePage.test.tsx
npm run build
```

Expected: focused tests pass and \`tsc -b && vite build\` exits 0.

- [ ] **Step 5: Commit the frontend slice.**

```bash
git add frontend/src/api/modules/ai.ts \
  frontend/src/features/ai/AIWorkspacePage.tsx \
  frontend/src/features/ai/AIWorkspacePage.test.tsx \
  frontend/src/lib/i18n.ts
git commit -m "feat: add conversation authorization cards"
```

## Task 6: Cross-layer security, audit, and regression verification

**Files:**
- Modify: \`backend/tests/test_ai_workspace_authorization.py\`
- Modify: \`backend/tests/test_api_ai_authorization.py\`
- Modify: \`frontend/src/features/ai/AIWorkspacePage.test.tsx\`
- Optional docs update: \`README.md\` or the AI workspace operator guide only if an existing user-facing guide documents tool permissions.

- [ ] **Step 1: Add regression cases for security and failure paths.**

Assert no request/metadata/audit payload contains values matching \`cookie\`, \`authorization\`, \`bearer\`, \`api_key\`, \`provider\`, or \`internal\`; assert an expired/revoked grant cannot execute a chapter; assert a malformed model tool call creates no authorization request; assert a \`rejected\` tool result ends the loop after one call; assert audit actions include request creation, decision, grant revocation, and actual tool invocation.

- [ ] **Step 2: Run the full backend regression suite.**

```bash
../legado-hub-pytest-venv/bin/python -m pytest -q
```

Expected: all backend tests pass, including the existing 33-test AI/provider slice.

- [ ] **Step 3: Run the full frontend suite and production build.**

```bash
cd frontend
npm test -- --run
npm run build
```

Expected: all Vitest tests pass and the production build completes without TypeScript errors.

- [ ] **Step 4: Run an authenticated smoke test against the local server.**

Create a temporary user token with \`ai.run\` and \`book_sources.read\`, send a character-analysis message, verify the response is \`authorization_required\` and the source executor has zero calls, approve \`once\`, verify exactly one search/toc/chapter chain, then repeat the decision and verify no additional calls. Test \`deny\` in a second conversation and verify the assistant explicitly refuses to use model memory as evidence.

- [ ] **Step 5: Review the diff and commit the verification updates.**

```bash
git diff --check
git status --short
git log --oneline -8
git add backend/tests frontend/src
git commit -m "test: verify conversation authorization boundaries"
```

Do not stage \`.vite\`, virtual environments, databases, credentials, or unrelated legacy worktree changes.

## Task 7: Handoff and integration

- [ ] **Step 1: Confirm the implementation plan is fully checked off and the design acceptance criteria are met.**
- [ ] **Step 2: Run \`git diff origin/main...HEAD --stat\` and inspect every changed file for secret leakage, migration regressions, and API contract drift.**
- [ ] **Step 3: Push the feature commits to the configured \`main\` remote only after the user requests deployment/push, and report commit IDs plus test commands/output.**
