# Super Admin Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the frontend into a single authenticated control plane that uses the new backend API contract for security administration, source operations, engine diagnostics, and AI/translation/novel workspaces.

**Architecture:** Keep React + Vite, but reorganize the app into an explicit shell (`app/`), typed API layer (`api/`), feature modules (`features/`), and shared UI components (`components/`). The console enforces RBAC in route/action guards and renders operational diagnostics from the backend response envelope.

**Tech Stack:** React 18, TypeScript, Vite, React Router, Axios, Vitest, React Testing Library, Sonner

---

> **Git note:** this working copy currently has no `.git`. Replace each “Commit” step with a filesystem checkpoint under `docs/superpowers/reports/checkpoints/`.

## File Structure

```text
frontend/src/
├── app/
│   ├── AppShell.tsx                               # route shell + nav + auth bootstrap
│   ├── router.tsx                                 # route tree
│   └── providers/AuthProvider.tsx                 # auth/session context
├── api/
│   ├── client.ts                                  # axios instance + refresh interceptors
│   ├── types.ts                                   # response/meta/shared payloads
│   └── modules/
│       ├── auth.ts
│       ├── admin.ts
│       ├── dashboard.ts
│       ├── engine.ts
│       ├── sources.ts
│       ├── ai.ts
│       ├── translation.ts
│       ├── novel.ts
│       └── system.ts
├── features/
│   ├── auth/LoginPage.tsx
│   ├── dashboard/DashboardPage.tsx
│   ├── sources/SourceListPage.tsx
│   ├── engine/EngineRunsPage.tsx
│   ├── admin/AdminUsersPage.tsx
│   ├── admin/AdminAuditPage.tsx
│   ├── ai/AITasksPage.tsx
│   ├── translation/TranslationJobsPage.tsx
│   ├── novel/NovelTasksPage.tsx
│   └── system/SystemSettingsPage.tsx
├── components/
│   ├── layout/ConsoleLayout.tsx
│   └── diagnostics/RunTimeline.tsx
├── lib/permissions.ts
├── test/setup.ts
└── main.tsx
frontend/package.json
frontend/vitest.config.ts
```

### Task 1: Add frontend test tooling and app shell skeleton

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/app/AppShell.tsx`
- Create: `frontend/src/app/router.tsx`
- Modify: `frontend/src/main.tsx`
- Test: `frontend/src/app/router.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { router } from './router'

test('unknown routes redirect to login when unauthenticated', async () => {
  render(<MemoryRouter initialEntries={['/missing']}><AppShell router={router} /></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: /sign in/i })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- --run frontend/src/app/router.test.tsx`  
Expected: FAIL because the `test` script and app shell do not exist.

- [ ] **Step 3: Write minimal implementation**

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest"
  },
  "devDependencies": {
    "vitest": "^2.0.5",
    "jsdom": "^24.1.1",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.8"
  }
}
```

```tsx
export function AppShell() {
  return <RouterProvider router={router} />
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- --run frontend/src/app/router.test.tsx`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item frontend/src/app/AppShell.tsx docs/superpowers/reports/checkpoints/2026-07-07-console-task1.tsx`  
Expected: checkpoint file exists.

### Task 2: Build auth/session provider and typed API client

**Files:**
- Create: `frontend/src/app/providers/AuthProvider.tsx`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/modules/auth.ts`
- Create: `frontend/src/lib/permissions.ts`
- Test: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
import { apiClient } from './client'

test('client retries the original request after refresh succeeds', async () => {
  const result = await apiClient.get('/api/dashboard')
  expect(result.meta).toBeDefined()
})
```

```tsx
test('auth provider exposes permissions from the current user payload', async () => {
  render(<AuthProvider><PermissionProbe permission="engine.deploy" /></AuthProvider>)
  expect(await screen.findByText('allowed')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend run test -- --run frontend/src/api/client.test.ts`  
Expected: FAIL because auth provider and typed client do not exist.

- [ ] **Step 3: Write minimal implementation**

```ts
export interface ApiEnvelope<T> {
  success: boolean
  code: string
  message: string
  data: T
  meta: Record<string, unknown>
  trace_id: string | null
}
```

```tsx
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null)
  const value = useMemo(() => ({ session, setSession, hasPermission: (name: string) => session?.permissions.includes(name) ?? false }), [session])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix frontend run test -- --run frontend/src/api/client.test.ts`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item frontend/src/api/client.ts docs/superpowers/reports/checkpoints/2026-07-07-console-task2.ts`  
Expected: checkpoint file exists.

### Task 3: Replace old dashboard/source pages with new API-backed operational views

**Files:**
- Create: `frontend/src/api/modules/dashboard.ts`
- Create: `frontend/src/api/modules/sources.ts`
- Create: `frontend/src/features/dashboard/DashboardPage.tsx`
- Create: `frontend/src/features/sources/SourceListPage.tsx`
- Create: `frontend/src/components/layout/ConsoleLayout.tsx`
- Test: `frontend/src/features/sources/SourceListPage.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
test('source list renders current status, published version, and latest run grade', async () => {
  render(<SourceListPage />)
  expect(await screen.findByText('Published')).toBeInTheDocument()
  expect(await screen.findByText('Latest grade')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- --run frontend/src/features/sources/SourceListPage.test.tsx`  
Expected: FAIL because the new feature module does not exist.

- [ ] **Step 3: Write minimal implementation**

```tsx
export function SourceListPage() {
  const { data, isLoading } = useSourceListQuery()
  if (isLoading) return <div>Loading</div>
  return <SourceTable rows={data.items} columns={["name", "status", "publishedVersion", "latestGrade"]} />
}
```

```ts
export async function listBookSources(params: SourceListParams) {
  return apiClient.get<ApiEnvelope<SourceRow[]>>('/api/sources/book_sources', { params })
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- --run frontend/src/features/sources/SourceListPage.test.tsx`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item frontend/src/features/sources/SourceListPage.tsx docs/superpowers/reports/checkpoints/2026-07-07-console-task3.tsx`  
Expected: checkpoint file exists.

### Task 4: Add engine diagnostics and security administration workspaces

**Files:**
- Create: `frontend/src/api/modules/engine.ts`
- Create: `frontend/src/api/modules/admin.ts`
- Create: `frontend/src/features/engine/EngineRunsPage.tsx`
- Create: `frontend/src/features/admin/AdminUsersPage.tsx`
- Create: `frontend/src/features/admin/AdminAuditPage.tsx`
- Create: `frontend/src/components/diagnostics/RunTimeline.tsx`
- Test: `frontend/src/features/engine/EngineRunsPage.test.tsx`

- [ ] **Step 1: Write the failing tests**

```tsx
test('engine runs page shows step timeline and deployment decision', async () => {
  render(<EngineRunsPage />)
  expect(await screen.findByText('search')).toBeInTheDocument()
  expect(await screen.findByText('deployment decision')).toBeInTheDocument()
})
```

```tsx
test('admin users page hides destructive actions without permission', async () => {
  render(<AdminUsersPage />)
  expect(screen.queryByRole('button', { name: /delete user/i })).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend run test -- --run frontend/src/features/engine/EngineRunsPage.test.tsx`  
Expected: FAIL because engine/admin workspaces do not exist.

- [ ] **Step 3: Write minimal implementation**

```tsx
export function EngineRunsPage() {
  const runs = useEngineRunsQuery()
  return <RunTimeline runs={runs.data ?? []} />
}
```

```tsx
export function AdminUsersPage() {
  const { hasPermission } = useAuth()
  return <UserTable canDelete={hasPermission('users.delete')} />
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix frontend run test -- --run frontend/src/features/engine/EngineRunsPage.test.tsx`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item frontend/src/features/engine/EngineRunsPage.tsx docs/superpowers/reports/checkpoints/2026-07-07-console-task4.tsx`  
Expected: checkpoint file exists.

### Task 5: Add AI/translation/novel/system workspaces and build verification

**Files:**
- Create: `frontend/src/api/modules/ai.ts`
- Create: `frontend/src/api/modules/translation.ts`
- Create: `frontend/src/api/modules/novel.ts`
- Create: `frontend/src/api/modules/system.ts`
- Create: `frontend/src/features/ai/AITasksPage.tsx`
- Create: `frontend/src/features/translation/TranslationJobsPage.tsx`
- Create: `frontend/src/features/novel/NovelTasksPage.tsx`
- Create: `frontend/src/features/system/SystemSettingsPage.tsx`
- Test: `frontend/src/features/system/SystemSettingsPage.test.tsx`

- [ ] **Step 1: Write the failing tests**

```tsx
test('system settings page shows provider health and quota panels', async () => {
  render(<SystemSettingsPage />)
  expect(await screen.findByText('Provider health')).toBeInTheDocument()
  expect(await screen.findByText('Quota policies')).toBeInTheDocument()
})
```

```tsx
test('ai tasks page shows provider and model for each task', async () => {
  render(<AITasksPage />)
  expect(await screen.findByText('provider')).toBeInTheDocument()
  expect(await screen.findByText('model')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend run test -- --run frontend/src/features/system/SystemSettingsPage.test.tsx`  
Expected: FAIL because these workspaces do not exist.

- [ ] **Step 3: Write minimal implementation**

```tsx
export function SystemSettingsPage() {
  const providerHealth = useProviderHealthQuery()
  const quotas = useQuotaPoliciesQuery()
  return <SystemPanels providerHealth={providerHealth.data ?? []} quotas={quotas.data ?? []} />
}
```

```tsx
export function AITasksPage() {
  const tasks = useAITasksQuery()
  return <TaskTable rows={tasks.data ?? []} columns={["name", "status", "provider", "model", "cost"]} />
}
```

- [ ] **Step 4: Run tests and build to verify they pass**

Run: `npm --prefix frontend run test -- --run frontend/src/features/system/SystemSettingsPage.test.tsx; npm --prefix frontend run build`  
Expected: tests PASS and Vite build succeeds.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item frontend/src/features/system/SystemSettingsPage.tsx docs/superpowers/reports/checkpoints/2026-07-07-console-task5.tsx`  
Expected: checkpoint file exists.
