# Frontend Pagination Request Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shared server-pagination hook emit the backend's `page/page_size/search` query contract directly, removing repeated adapters from every routed list page without changing pagination, search, retry, or stale-response behavior.

**Architecture:** `useServerPagination` remains the single owner of page/search state and will expose a required `ServerPageRequest` shaped like the API query parameters. Existing API modules already accept `PaginatedQueryParams`, so each page can pass its list function directly. The standalone `toPaginatedQueryParams` helper and its test become unnecessary after all callers migrate.

**Tech Stack:** React 18, TypeScript 5, Vitest, Testing Library, Vite.

---

### Task 1: Lock the new hook request contract with failing tests

**Files:**
- Modify: `frontend/src/hooks/useServerPagination.test.ts`

- [ ] **Step 1: Change the request assertions to the backend shape**

Replace every expected hook request containing `pageSize` with `page_size`:

```ts
expect(load).toHaveBeenCalledWith({ page: 1, page_size: 2, search: '' })
expect(load).toHaveBeenLastCalledWith({ page: 2, page_size: 1, search: '' })
expect(load).toHaveBeenLastCalledWith({ page: 1, page_size: 2, search: 'beta' })
```

Keep the existing response, retry, stale-response, and unmount assertions unchanged.

- [ ] **Step 2: Run the hook tests and verify they fail before implementation**

Run from `frontend`:

```bash
npm exec vitest run src/hooks/useServerPagination.test.ts
```

Expected: FAIL because the current hook still calls `load` with `pageSize`.

### Task 2: Make the shared hook emit API query parameters

**Files:**
- Modify: `frontend/src/hooks/useServerPagination.ts:5-75`

- [ ] **Step 1: Define the snake-case request type**

Use this request contract while keeping the public option name `pageSize` for component ergonomics:

```ts
export interface ServerPageRequest {
  page: number
  page_size: number
  search: string
}
```

- [ ] **Step 2: Pass `page_size` to the loader**

In `requestPage`, call the loader with:

```ts
const response = await loadRef.current({
  page: requestedPage,
  page_size: pageSizeRef.current,
  search,
})
```

Do not change request sequencing, request IDs, stale-response protection, retry targets, or normalized metadata.

- [ ] **Step 3: Run the hook tests and verify they pass**

Run:

```bash
npm exec vitest run src/hooks/useServerPagination.test.ts
```

Expected: all six hook tests pass.

### Task 3: Remove per-page pagination adapters

**Files:**
- Modify: `frontend/src/features/admin/AdminAuditPage.tsx`
- Modify: `frontend/src/features/admin/AdminUsersPage.tsx`
- Modify: `frontend/src/features/admin/ApiKeysPage.tsx`
- Modify: `frontend/src/features/ai/AITasksPage.tsx`
- Modify: `frontend/src/features/ai/AIWorkspacePage.tsx`
- Modify: `frontend/src/features/engine/EngineRunsPage.tsx`
- Modify: `frontend/src/features/novel/NovelTasksPage.tsx`
- Modify: `frontend/src/features/operations/AgentRunsPage.tsx`
- Modify: `frontend/src/features/operations/EventDeliveriesPage.tsx`
- Modify: `frontend/src/features/operations/JobsPage.tsx`
- Modify: `frontend/src/features/operations/ReviewQueuePage.tsx`
- Modify: `frontend/src/features/operations/SourceBuildsPage.tsx`
- Modify: `frontend/src/features/sources/SourceHealthPage.tsx`
- Modify: `frontend/src/features/sources/SourceListPage.tsx`
- Modify: `frontend/src/features/translation/TranslationJobsPage.tsx`

- [ ] **Step 1: Remove the adapter imports**

Delete each page's import:

```ts
import { toPaginatedQueryParams } from '@/lib/pagination'
```

- [ ] **Step 2: Pass the list API function directly**

Change each pagination loader from:

```ts
load: (request) => listRows(toPaginatedQueryParams(request))
```

to:

```ts
load: listRows
```

Apply this to every list function, including all three loaders in `EngineRunsPage`.

- [ ] **Step 3: Verify no routed page still imports the adapter**

Run:

```bash
rg -n "toPaginatedQueryParams" frontend/src/features frontend/src/pages
```

Expected: no matches.

### Task 4: Delete the now-unused conversion helper

**Files:**
- Modify: `frontend/src/lib/pagination.ts`
- Modify: `frontend/src/lib/pagination.test.ts`

- [ ] **Step 1: Remove the obsolete request conversion code**

Remove the `PaginatedQueryParams` import, the `PaginatedRequest` interface, and `toPaginatedQueryParams`. Keep `normalizePageMeta` and its validation behavior unchanged.

- [ ] **Step 2: Remove only the obsolete helper test**

Change the test import to:

```ts
import { normalizePageMeta } from './pagination'
```

Delete the `describe('toPaginatedQueryParams', ...)` block; retain all four metadata tests.

- [ ] **Step 3: Verify the helper has no remaining references**

Run:

```bash
rg -n "PaginatedRequest|toPaginatedQueryParams" frontend/src
```

Expected: no matches.

### Task 5: Run the frontend verification suite and commit

**Files:**
- No additional source files.

- [ ] **Step 1: Run focused pagination tests**

```bash
npm exec vitest run src/hooks/useServerPagination.test.ts src/lib/pagination.test.ts
```

Expected: all tests pass.

- [ ] **Step 2: Run the affected routed-page tests**

```bash
npm exec vitest run \
  src/features/sources/SourceListPage.test.tsx \
  src/features/sources/SourceHealthPage.test.tsx \
  src/features/operations/EventDeliveriesPage.test.tsx \
  src/features/operations/ReviewQueuePage.test.tsx \
  src/features/operations/SourceBuildsPage.test.tsx \
  src/features/engine/EngineRunsPage.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 3: Type-check and build**

```bash
npm run build
```

Expected: `tsc -b` and the Vite production build exit with code 0.

- [ ] **Step 4: Check the diff and commit**

```bash
git diff --check
git status --short
git add frontend/src/hooks/useServerPagination.ts frontend/src/hooks/useServerPagination.test.ts frontend/src/lib/pagination.ts frontend/src/lib/pagination.test.ts frontend/src/features
git commit -m "refactor: emit backend pagination query contract"
```

Expected: clean diff check and one commit containing only the pagination contract refactor.
