# Super Admin Console Design

> Date: 2026-07-07  
> Workspace: `C:\Users\lihuo\Desktop\legado-hub`  
> Subproject: 3 / 4  
> Runtime target: local Vite frontend against the authenticated main backend API  
> Git note: this workspace currently has no `.git`; write files directly and use filesystem checkpoints instead of commits.

---

## 1. Goal

Replace the current old-contract frontend with a unified operational console that speaks only to the new authenticated main API. The console must cover identity/security administration, source operations, engine diagnostics, AI/translation/novel workspaces, and system settings in one coherent React application.

## 2. Confirmed decisions

- This is a full control-plane rebuild, not a page-by-page patch of the old UI.
- The console remains on React + Vite; the stack is not replaced.
- The console consumes the new `/api/*` contract only.
- RBAC is enforced in the UI at route level and action level.
- Source operations, engine diagnostics, user/security management, and AI/translation/novel workspaces all live inside one application shell.

## 3. Scope

### In scope

- Login, refresh, logout, session awareness
- Menu shell, nested routes, permission guards
- Dashboard operational summaries
- Source lists, version history, test history, deployment/rollback views
- Engine test center and diagnostics views
- User/role/permission/API-key/session/audit administration
- AI / translation / novel workspaces and task detail pages
- System settings, provider settings, health status, quota displays

### Out of scope

- Keeping old route/layout contracts alive
- A second independent frontend for AI/translation/novel
- Replacing React with another framework

## 4. Information architecture

The first release contains these primary sections:

1. Login & security
2. Dashboard overview
3. Source management
4. Engine / diagnostics center
5. Identity & permissions
6. AI workspace
7. Translation & novel workspace
8. System settings & provider management

## 5. Frontend architecture

The frontend is reorganized into:

- `app/`: shell, routing, providers, auth bootstrap
- `api/`: typed client, token attach/refresh, module clients, response normalization
- `features/`: domain-specific UI modules (dashboard, sources, engine, admin, ai, translation, novel, system)
- `components/`: shared UI widgets such as tables, badges, dialogs, log viewers, diagnostics panels
- `lib/`: permission helpers, formatters, route metadata

The application should not keep page-local ad hoc axios calls. Data access is centralized by module.

## 6. UX principles

- Show why an operation failed, not just that it failed.
- Treat long-running actions as tracked tasks with visible status.
- Prefer list -> detail -> diagnostics navigation for operational work.
- Keep version diffs, response samples, audit records, and run timelines one click away from the source or task that produced them.
- Hide or disable unauthorized actions based on RBAC metadata.

## 7. Contract alignment

The current frontend still calls old endpoints such as `/dashboard/stats`, `/sources/book`, `/health/check`, and `/output/*`. The new console must instead consume the authenticated main API families:

- `/api/auth/*`
- `/api/admin/*`
- `/api/sources/*`
- `/api/engine/*`
- `/api/dashboard/*`
- `/api/health/*`
- `/api/export/*`
- `/api/ai/*`
- `/api/translation/*`
- `/api/novel/*`
- `/api/system/*`

Response handling must respect the new envelope shape with `data`, `meta`, and `trace_id`.

## 8. Key screens

### Source management

- List/filter book and RSS sources
- Inspect current published version
- Inspect candidate/quarantined/rolled-back versions
- Read run history, diagnostics, and deployment decisions
- Trigger test/repair/regression/deploy actions

### Engine diagnostics center

- Submit URL-based generation
- Run real tests and view step timelines
- Compare candidate vs published version
- Inspect quality-gate decisions and diffs

### Security administration

- Manage users, roles, permissions, API keys, sessions
- Search audit logs
- Inspect auth/session events

### AI / translation / novel workspaces

- Submit tasks
- Inspect task status and results
- Review provider/model information
- Retry/cancel eligible tasks

### System settings

- Provider configuration
- Quotas and limits
- Health state and operational settings

## 9. Testing strategy

- Add Vitest + React Testing Library for route guards, auth bootstrap, and complex domain views
- Add API-client tests for refresh behavior and response normalization
- Keep `npm run build` as a required verification step
- Prefer mocked HTTP module tests for most UI behavior, with a small number of local smoke checks against the running backend

## 10. Risks and constraints

- Scope is large; the shell, auth client, and domain modules must be decomposed cleanly.
- Route/action authorization cannot drift from backend RBAC names.
- Diagnostic-heavy screens can become unreadable if response samples and diffs are not structured deliberately.
- The backend contract must be stable enough before the later domain pages are finalized.

## 11. Acceptance criteria

This subproject is complete when:

- The frontend authenticates against the new main API and refreshes sessions correctly
- Old route contracts are fully retired from the frontend
- Users can operate sources, engine, security admin, AI, translation, novel, and system settings in one shell
- RBAC controls routes and actions in the UI
- Diagnostic records from subproject 2 are visible and usable
- The application builds locally and supports local development against the Python 3.13 backend
