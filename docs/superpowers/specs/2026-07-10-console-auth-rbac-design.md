# 2026-07-10 Console Auth And RBAC Design

## Goal

Connect the console shell to the existing `/api/auth` service so an operator can log in, recover a tab session, refresh an expired access token, and access only routes permitted by the backend RBAC model.

## Current Contract And Normalization

The backend login endpoint returns `access_token`, `refresh_token`, and a permissions list. The refresh endpoint returns a replacement `access_token`; `/auth/me` returns the authenticated `user_id`, permissions, and session ID. The frontend will normalize these payloads into its existing camelCase `AuthSession` shape after login and refresh.

The console will treat backend permission strings as authoritative. It will not infer elevated permissions from route names or frontend role labels.

## Session Lifecycle

- Access tokens remain in React memory only.
- The refresh token is stored in `sessionStorage` under one dedicated key, allowing a page reload in the same tab to recover while clearing the credential when the tab is closed.
- On application bootstrap, the provider reads the refresh token, calls `/auth/refresh`, then `/auth/me`, and marks initialization complete.
- API requests receive the current access token from a mutable client binding.
- A single `401` refreshes the session and retries the originating request. Concurrent refresh attempts share one in-flight promise.
- Login failure displays the backend-safe error message. Refresh failure clears memory and `sessionStorage`, then routes protected access to `/login`.
- Logout calls `/auth/logout` while an access token is available, then always clears local state.

## Routing And RBAC

`RequireAuth` wraps every console route except `/login`. It waits for session initialization, redirects unauthenticated users to `/login`, and preserves the intended destination.

`RequirePermission` receives one or more backend permission strings. It renders an access-denied route for an authenticated user without the required permission. Routes map to the APIs they invoke, for example source-health requires `book_sources.read`, system settings requires `system.settings.manage`, and admin users requires `users.read`.

The shell navigation uses the same permission metadata to hide unavailable entries. Route guards remain mandatory because hidden navigation is not authorization.

## User Interface

The login page becomes a compact username/password form with submit, pending, validation, and error states. A successful login redirects to the preserved target or `/sources`. The authenticated shell displays the current username and an icon-only logout control with an accessible label and tooltip.

## Tests

Frontend tests cover DTO normalization, login success/failure, session bootstrap refresh, exactly-once `401` refresh-and-retry, refresh failure cleanup, unauthenticated route redirect, and permission-denied rendering. Existing backend auth flow tests remain the API contract regression suite.

## Non-Goals

This work does not alter backend token signing, role persistence, permission assignment, password reset, multi-factor authentication, or cross-tab session synchronization.
