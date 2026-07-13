# Console Auth And RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable real console login, refresh-backed session recovery, and backend-permission route protection.

**Architecture:** A small auth API adapter normalizes backend snake_case responses and fetches identity from `/auth/me`. `AuthProvider` owns the in-memory access token and sessionStorage refresh token, while a configured Axios client delegates refresh failures to it. Reusable route guards enforce authentication and permissions independently of navigation visibility.

**Tech Stack:** React 18, TypeScript, React Router, Axios, Vitest, Testing Library, FastAPI auth API.

---

### Task 1: Normalize Backend Auth Payloads

**Files:**
- Modify: `frontend/src/api/modules/auth.ts`
- Modify: `frontend/src/api/types.ts`
- Create: `frontend/src/api/modules/auth.test.ts`

- [ ] Write failing tests for mapping `access_token`, `refresh_token`, and `/auth/me` into `AuthSession`.
- [ ] Run `npm test -- --run src/api/modules/auth.test.ts` and confirm the missing mapper fails.
- [ ] Add `createAuthSession(tokens, identity, previousRefreshToken?)`, preserving refresh token on refresh responses and mapping `user_id` to string `user.id`.
- [ ] Run the focused test again and confirm it passes.

### Task 2: Add Provider-Owned Session Lifecycle

**Files:**
- Modify: `frontend/src/app/providers/AuthProvider.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/client.test.tsx`

- [ ] Add failing tests proving bootstrap refresh restores a session and a failed refresh clears it.
- [ ] Run `npm test -- --run src/api/client.test.tsx` and confirm failures.
- [ ] Add a `configureAuthClient` binding, single-flight refresh promise, `sessionStorage` refresh-token helpers, `initializing` state, `login`, and `logout` methods to `AuthProvider`.
- [ ] Configure `apiClient` to attach the current access token, refresh exactly once on a `401`, retry the originating request, and clear the provider session when refresh fails.
- [ ] Run the focused client/provider tests and confirm they pass.

### Task 3: Implement Login Flow

**Files:**
- Modify: `frontend/src/features/auth/LoginPage.tsx`
- Create: `frontend/src/features/auth/LoginPage.test.tsx`

- [ ] Add failing tests for username/password submission, failed-login error rendering, and navigation after successful `useAuth().login()`.
- [ ] Run `npm test -- --run src/features/auth/LoginPage.test.tsx` and confirm failure against the placeholder page.
- [ ] Replace the placeholder with a controlled form, disabled pending submit button, API-safe error state, and redirect to `location.state.from` or `/sources`.
- [ ] Run the focused login page test and confirm it passes.

### Task 4: Protect Routes And Apply RBAC

**Files:**
- Create: `frontend/src/app/router/RequireAuth.tsx`
- Create: `frontend/src/app/router/RequirePermission.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/components/layout/ConsoleLayout.tsx`
- Create: `frontend/src/app/router/guards.test.tsx`

- [ ] Add failing tests for unauthenticated redirect to `/login`, permitted route rendering, and permission-denied rendering.
- [ ] Run `npm test -- --run src/app/router/guards.test.tsx` and confirm missing guards fail.
- [ ] Implement `RequireAuth` with initialization wait and preserved destination; implement `RequirePermission` using `useAuth().hasPermission` and an access-denied display.
- [ ] Wrap each console route with its matching backend permission and render the login route without the console shell.
- [ ] Add authenticated username and an icon-only logout control with title and aria label to the console layout.
- [ ] Run guard tests and confirm they pass.

### Task 5: Regression Verification

**Files:**
- Modify: `docs/superpowers/reports/checkpoints/2026-07-10-console-auth-rbac.md`

- [ ] Run `npm test -- --run src/api/modules/auth.test.ts src/api/client.test.tsx src/features/auth/LoginPage.test.tsx src/app/router/guards.test.tsx`.
- [ ] Run `npm run build`.
- [ ] Run `backend/.venv/Scripts/python.exe -m pytest tests/test_api_auth_main.py -q` from the project root.
- [ ] Record exact results and any residual browser-only validation in the checkpoint report.

## Completion Note

The project root is not a Git repository. Do not initialize a repository, commit, or change Git configuration during this work.
