# Unified Server Pagination and List Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Replace duplicated and unbounded list loading with one tested server-pagination/search module shared by all growing console lists.

**Architecture:** A generic frontend hook owns page/search state, stale-request protection, retry targets, and normalized metadata. A presentational toolbar owns search and navigation controls. Each API adapter translates its endpoint into the common request/response contract; backend repositories perform filtering, counting, ordering, and OFFSET/LIMIT before serialization.

**Tech Stack:** React 18, TypeScript, Vitest Testing Library, FastAPI, Python 3.12, SQLAlchemy/SQLite, pytest.

---

### Task 1: Shared pagination contract and metadata normalizer

**Files**
- Modify frontend/src/api/types.ts
- Create frontend/src/lib/pagination.ts
- Create frontend/src/lib/pagination.test.ts

- [ ] Write failing tests for complete metadata, missing metadata, empty rows, fractional page values, and non-positive page sizes.
- [ ] Run:
    
    cd frontend
    npm test -- --run src/lib/pagination.test.ts
    
  Confirm RED because the normalizer is absent.
- [ ] Add this type to api/types.ts and a normalizer to lib/pagination.ts:

~~~ts
export interface PaginatedMeta {
  page: number
  page_size: number
  total: number
  total_pages: number
  search?: string
}

export function normalizePageMeta(
  meta: Record<string, unknown>,
  requestedPage: number,
  defaultPageSize: number,
  rowCount: number,
): PaginatedMeta {
  const pageSize = integerAtLeast(meta.page_size, defaultPageSize, 1)
  const total = integerAtLeast(meta.total, rowCount, 0)
  const page = integerAtLeast(meta.page, requestedPage, 1)
  const calculatedPages = total > 0 ? Math.ceil(total / pageSize) : 1
  const totalPages = integerAtLeast(meta.total_pages, calculatedPages, 1)
  return {
    page,
    page_size: pageSize,
    total,
    total_pages: totalPages,
    search: typeof meta.search === 'string' ? meta.search : undefined,
  }
}
~~~

  Keep integerAtLeast private and reject NaN, fractions, and negative values.
- [ ] Run the same test command and confirm GREEN.
- [ ] Commit:
    
    git add frontend/src/api/types.ts frontend/src/lib/pagination.ts frontend/src/lib/pagination.test.ts
    git commit -m "feat: add shared pagination metadata contract"

### Task 2: Generic useServerPagination hook

**Files**
- Create frontend/src/hooks/useServerPagination.ts
- Create frontend/src/hooks/useServerPagination.test.ts

- [ ] Write failing tests using a deferred loader for initial page 1, page replacement, trimmed search to page 1, failed-page retry, stale response suppression, and unmount safety.
- [ ] Run:
    
    cd frontend
    npm test -- --run src/hooks/useServerPagination.test.ts
    
  Confirm RED.
- [ ] Implement this public contract:

~~~ts
export interface ServerPageRequest {
  page: number
  pageSize: number
  search: string
}

export interface UseServerPaginationOptions<T> {
  pageSize: number
  load: (request: ServerPageRequest) => Promise<ApiEnvelope<T[]>>
  initialSearch?: string
}

export function useServerPagination<T>(options: UseServerPaginationOptions<T>) {
  // rows, meta, searchInput, appliedSearch, loading, error
  // submitSearch, clearSearch, goToPage, retry, reload
}
~~~

  Increment a request id for every load, store the failed page/search retry target, normalize response metadata, replace rows, and ignore stale or unmounted responses. reload uses the last successful request; retry uses the failed request.
- [ ] Run:
    
    npm test -- --run src/lib/pagination.test.ts src/hooks/useServerPagination.test.ts
    
  Confirm GREEN, then commit:
    
    git add frontend/src/hooks/useServerPagination.ts frontend/src/hooks/useServerPagination.test.ts
    git commit -m "feat: add reusable server pagination hook"

### Task 3: Shared PaginationToolbar

**Files**
- Create frontend/src/components/data/PaginationToolbar.tsx
- Create frontend/src/components/data/PaginationToolbar.test.tsx

- [ ] Write failing tests for the search aria-label, trimmed search callback, clear callback, boundary button disabled state, loading disabled state, and no-results text.
- [ ] Run:
    
    cd frontend
    npm test -- --run src/components/data/PaginationToolbar.test.tsx
    
  Confirm RED.
- [ ] Implement a presentational component with props page, totalPages, total, searchInput, appliedSearch, loading, showSearch, searchLabel, onSearchInput, onSearch, onClearSearch, and onPageChange. It must not call an API; use existing Input and Button components and the Chinese labels 搜索、清空、上一页、下一页.
- [ ] Run the toolbar tests and commit:
    
    npm test -- --run src/components/data/PaginationToolbar.test.tsx
    git add frontend/src/components/data/PaginationToolbar.tsx frontend/src/components/data/PaginationToolbar.test.tsx
    git commit -m "feat: add shared pagination toolbar"

### Task 4: Migrate source inventory and health pages

**Files**
- Modify frontend/src/features/sources/SourceListPage.tsx
- Modify frontend/src/features/sources/SourceHealthPage.tsx
- Modify corresponding SourceListPage.test.tsx and SourceHealthPage.test.tsx
- Modify frontend/src/api/modules/sources.ts and sourceHealth.ts

- [ ] Add health-page regression assertions for page replacement and failed-page retry before replacing its local state.
- [ ] Run the two source page suites and confirm the new assertions fail.
- [ ] Adapt API loaders to accept request.page, request.pageSize, and request.search. Replace page-local rows/meta/request-id/pagination state with useServerPagination and render PaginationToolbar. Leave import, probe, recover, manual verification, and detail state local.
- [ ] Run:
    
    npm test -- --run src/features/sources/SourceListPage.test.tsx src/features/sources/SourceHealthPage.test.tsx src/features/sources/SourceListImportLink.test.tsx
    
  Confirm all existing source behavior remains green.
- [ ] Commit:
    
    git add frontend/src/features/sources frontend/src/api/modules/sources.ts frontend/src/api/modules/sourceHealth.ts
    git commit -m "refactor: share pagination state across source pages"

### Task 5: Standardize source backend pagination metadata

**Files**
- Modify backend/app/application/services/source_runtime_service.py
- Modify backend/app/application/services/source_health_admin_service.py
- Modify backend/app/interfaces/http/sources.py and source_health.py
- Modify backend/tests/test_api_source_import_export.py and test_api_source_health.py

- [ ] Add failing tests asserting total_pages; visible-source search-before-pagination; and health-inventory source-name/URL search plus status-before-pagination.
- [ ] Run:
    
    /tmp/legado-hub-pytest-venv/bin/pytest backend/tests/test_api_source_import_export.py backend/tests/test_api_source_health.py -q
    
  Confirm RED.
- [ ] Compute total_pages from the filtered total while preserving visibility predicates, page-size bounds, and repository-level COUNT/OFFSET/LIMIT. Add an optional search query to source health, pass it through SourceHealthAdminService, and filter BookSourceModel name/URL before COUNT/OFFSET/LIMIT.
- [ ] Run the focused pytest command and commit:
    
    git add backend/app/application/services/source_runtime_service.py backend/app/application/services/source_health_admin_service.py backend/app/interfaces/http/sources.py backend/app/interfaces/http/source_health.py backend/tests/test_api_source_import_export.py backend/tests/test_api_source_health.py
    git commit -m "feat: standardize source pagination metadata"

### Task 6: Paginate operation and review inventories

**Files**
- Modify backend/app/interfaces/http/events.py
- Modify backend/app/application/services/event_delivery_service.py, job_service.py, agent_runtime_service.py, source_review_service.py
- Modify backend/app/infrastructure/persistence/sqlite/event_delivery_repo_impl.py, job_repo_impl.py, agent_runtime_repo_impl.py, source_review_repo_impl.py
- Modify frontend/src/api/modules/operations.ts
- Create backend/tests/test_api_operations_pagination.py

- [ ] Write failing tests for jobs, deliveries, source builds, Agent runs, and review queue. Seed more than one page and assert bounded rows, total_pages, supported search/status filters, and unchanged detail endpoints.
- [ ] Run:
    
    /tmp/legado-hub-pytest-venv/bin/pytest backend/tests/test_api_operations_pagination.py -q
    
  Confirm RED.
- [ ] Add page/page_size/filter arguments to repository methods, count the filtered query, preserve existing ordering, and apply OFFSET/LIMIT in SQL.
- [ ] Thread the arguments through services and events.py query declarations. Update operation API adapters to accept page, page_size, search, and status where supported.
- [ ] Run the backend test plus:
    
    cd frontend
    npm test -- --run src/features/operations
    
  Commit:
    
    git add backend frontend/src/api/modules/operations.ts
    git commit -m "feat: paginate operation and review inventories"

### Task 7: Paginate admin, engine, AI, novel, and translation inventories

**Files**
- Modify backend/app/interfaces/http/admin.py, engine.py, ai.py, novel.py, translation.py
- Modify backend application services auth_service.py, source_runtime_service.py, ai_service.py, ai_workspace_service.py, novel_app_service.py, translation_service.py
- Modify the corresponding SQLite repositories auth_repo_impl.py, source_runtime_repo_impl.py, ai_runtime_repo_impl.py, ai_conversation_repo_impl.py, novel_repo_impl.py, translation_runtime_repo_impl.py
- Modify frontend API modules admin.ts, engine.ts, ai.ts, novel.ts, translation.ts
- Create backend/tests/test_api_list_pagination.py

- [ ] Write failing tests for users, audit logs, API keys, engine runs/deployments/source builds, AI tasks/conversations, novel books, and translation jobs. Assert bounded rows, total_pages, and stable-field search where supported; leave detail/actions/chunks unpaginated.
- [ ] Run:
    
    /tmp/legado-hub-pytest-venv/bin/pytest backend/tests/test_api_list_pagination.py -q
    
  Confirm RED.
- [ ] Implement database-level count and bounded queries, preserve existing sort and authorization, and return items plus common metadata from services.
- [ ] Add bounded HTTP query parameters and update TypeScript adapters without changing row serialization.
- [ ] Run:
    
    /tmp/legado-hub-pytest-venv/bin/pytest backend/tests/test_api_list_pagination.py backend/tests/test_api_admin_users.py backend/tests/test_api_engine_runtime.py -q
    
    cd frontend
    npm test -- --run src/api/modules/runtime-platform.test.ts
    
  Commit:
    
    git add backend frontend/src/api/modules/admin.ts frontend/src/api/modules/engine.ts frontend/src/api/modules/ai.ts frontend/src/api/modules/novel.ts frontend/src/api/modules/translation.ts
    git commit -m "feat: paginate admin and content list endpoints"

### Task 8: Migrate operation, admin, and content pages

**Files**
- Modify frontend pages under features/operations, features/admin, features/ai, features/novel, features/translation, and features/engine
- Modify the corresponding *.test.tsx files

- [ ] Add page-level assertions for initial page-size parameters, page replacement, page-one search requests, and preserved detail/mutation/SSE/manual-verification behavior.
- [ ] Run affected page tests and confirm the new assertions fail for missing query parameters or toolbar behavior.
- [ ] Replace unbounded useEffect list loaders and local pagination/search state with useServerPagination and PaginationToolbar. Keep selected rows, detail loading, mutation, and modal state local.
- [ ] Run:
    
    cd frontend
    npm test -- --run src/features/operations src/features/admin src/features/ai src/features/novel src/features/translation src/features/engine
    
- [ ] Commit:
    
    git add frontend/src/features/operations frontend/src/features/admin frontend/src/features/ai frontend/src/features/novel frontend/src/features/translation frontend/src/features/engine
    git commit -m "refactor: migrate console lists to shared pagination"

### Task 9: Remove duplicate logic and document compatibility

**Files**
- Inspect frontend/src/pages/SourcesPage.tsx and leave it as a compatibility layer if unreachable.
- Modify remaining frontend API list signatures and the pagination design spec only for discovered endpoint exceptions.
- Create barrel exports only if the project already uses them.

- [ ] Search:
    
    rg -n "list[A-Z][A-Za-z]+\\(\\)|set[A-Za-z]+\\(response\\.data\\)|page_size|totalPages" frontend/src/features frontend/src/pages frontend/src/api/modules
    
  Classify remaining calls as detail/lookup, fixed-size widget, stream, or migrated list.
- [ ] Delete only dead page-local page-meta, request-id, previous/next, and search-form helpers; keep route-specific adapters and row actions.
- [ ] Run:
    
    cd frontend
    npm run build
    npm test -- --run src/hooks src/components/data src/features/sources src/features/operations src/features/admin src/features/ai src/features/novel src/features/translation src/features/engine
    
- [ ] Commit:
    
    git add frontend docs/superpowers/specs/2026-07-16-unified-server-pagination-design.md
    git commit -m "refactor: remove duplicated list pagination logic"

### Task 10: Full verification, deployment, and GitHub integration

**Files**
- No source-file additions; verify release commits and built assets.

- [ ] Run all backend tests:
    
    /tmp/legado-hub-pytest-venv/bin/pytest backend/tests -q
    
  Record unrelated baseline failures separately; all newly touched tests must pass.
- [ ] Run frontend tests and build:
    
    cd frontend
    npm test -- --run
    npm run build
- [ ] Restart only the uvicorn process whose working directory is /tmp/legado-hub-release/backend, preserve backend/.env and DB_PATH, and poll /api/status until env=prod.
- [ ] Log in without printing tokens and verify /api/sources/visible?page=1&page_size=1&search=... returns bounded data and page/page_size/total/total_pages/search metadata. Fetch the built list-page asset and assert shared toolbar labels are present.
- [ ] Verify git status, push origin main, and report commit, tests, build, API status, and unrelated baseline failures without exposing credentials.
