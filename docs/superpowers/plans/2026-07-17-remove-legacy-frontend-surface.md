# Remove Legacy Frontend Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the unreachable pre-console frontend pages, duplicate Axios API module, and obsolete shell so the build contains one routed UI architecture and one API client.

**Architecture:** `frontend/src/app/router.tsx` and `AppShell.tsx` are the authoritative entry points. They route only `features/*`, use `apiClient` through `api/modules/*`, and render `AppConsoleShell`; the old `pages/*`, `api/index.ts`, and `AppLayout.tsx` have no imports and can be deleted without changing reachable routes. A router regression test will lock the existing wildcard redirect for legacy paths.

**Tech Stack:** React 18, React Router 6, TypeScript 5, Vitest, Testing Library, Vite.

---

### Task 1: Lock legacy route behavior before deletion

**Files:**
- Modify: `frontend/src/app/router.test.tsx`

- [ ] **Step 1: Add a regression test for old paths**

Append this test to the existing router tests:

```tsx
test.each(['/dashboard', '/search', '/test', '/health', '/export'])('legacy path %s redirects to login', async (path) => {
  render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider bootstrapSession={null}>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByRole('heading', { name: /sign in/i })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the router test**

```bash
npm exec vitest run src/app/router.test.tsx
```

Expected: all router tests pass, proving these paths are already handled by the current wildcard redirect rather than the deleted components.

### Task 2: Remove unreachable duplicate modules

**Files:**
- Delete: `frontend/src/api/index.ts`
- Delete: `frontend/src/components/layout/AppLayout.tsx`
- Delete: `frontend/src/pages/DashboardPage.tsx`
- Delete: `frontend/src/pages/ExportPage.tsx`
- Delete: `frontend/src/pages/HealthPage.tsx`
- Delete: `frontend/src/pages/SearchTestPage.tsx`
- Delete: `frontend/src/pages/SourcesPage.tsx`
- Delete: `frontend/src/pages/TestPage.tsx`

- [ ] **Step 1: Verify the deletion set has no reachable imports**

Run:

```bash
rg -n "from ['\"]@/api['\"]|from ['\"].*AppLayout['\"]|from ['\"]@/pages|from ['\"].*pages/" frontend/src --glob '!api/index.ts' --glob '!pages/**' --glob '!components/layout/AppLayout.tsx' || true
```

Expected: no imports of the legacy modules outside the files being removed.

- [ ] **Step 2: Delete the files**

Remove only the seven listed files. Do not alter `frontend/src/api/client.ts`, `frontend/src/api/modules/*`, `AppConsoleShell.tsx`, or any `features/*` page.

- [ ] **Step 3: Verify the source tree has one active client and shell**

Run:

```bash
rg -n "axios\.create|export default function AppLayout|from ['\"]@/api['\"]|from ['\"].*AppLayout['\"]" frontend/src || true
```

Expected: `axios.create` appears only in `frontend/src/api/client.ts`; no `@/api` legacy barrel or `AppLayout` references remain.

### Task 3: Verify and commit the cleanup

**Files:**
- No additional source files.

- [ ] **Step 1: Run router and representative feature tests**

```bash
npm exec vitest run \
  src/app/router.test.tsx \
  src/features/sources/SourceListPage.test.tsx \
  src/features/operations/JobsPage.test.tsx \
  src/features/system/SystemSettingsLayout.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 2: Type-check and build**

```bash
npm run build
```

Expected: TypeScript and Vite both exit with code 0.

- [ ] **Step 3: Check and commit only this cleanup**

```bash
git diff --check
git status --short
git add frontend/src/app/router.test.tsx frontend/src/api/index.ts frontend/src/components/layout/AppLayout.tsx frontend/src/pages
git commit -m "refactor: remove legacy frontend surface"
```

Expected: one cleanup commit with no changes to the active feature architecture.
