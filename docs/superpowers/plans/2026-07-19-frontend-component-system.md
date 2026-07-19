# Frontend Component System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the authenticated console UI migration so shared layout, data, form, detail, status, and pagination components own all repeated presentation behavior.

**Architecture:** Keep API modules and `useServerPagination` as the only data boundary. Build presentation-only components under `components/layout`, `components/data`, `components/form`, and `components/detail`; feature pages retain only DTO mapping, business actions, and column definitions. Migrate pages incrementally and enforce the boundary with Vitest source-contract tests.

**Tech Stack:** React 18, TypeScript, Vitest, Testing Library, Tailwind utility classes, existing local UI primitives.

---

### Task 1: Lock the Component Boundary With Failing Contract Tests

**Files:**
- Create: `frontend/src/architecture/component-boundaries.test.ts`
- Test: `frontend/src/architecture/component-boundaries.test.ts`
- Reference: `docs/superpowers/specs/2026-07-19-frontend-component-system-design.md`

- [ ] **Step 1: Write the failing architectural tests**

```tsx
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test } from 'vitest'

const featureRoot = resolve(process.cwd(), 'src/features')
const read = (relativePath: string) => readFileSync(resolve(featureRoot, relativePath), 'utf8')

describe('console component boundaries', () => {
  test.each([
    'operations/JobsPage.tsx',
    'operations/ReviewQueuePage.tsx',
    'operations/EventDeliveriesPage.tsx',
    'operations/SourceBuildsPage.tsx',
    'sources/SourceHealthDetailPage.tsx',
  ])('%s delegates table markup to DataTable', (relativePath) => {
    expect(read(relativePath)).not.toMatch(/<table\b/)
    expect(read(relativePath)).toContain("@/components/data/DataTable")
  })

  test('production feature modules do not call fetch directly', () => {
    const sourceFiles = [
      'operations/JobsPage.tsx',
      'operations/ReviewQueuePage.tsx',
      'operations/EventDeliveriesPage.tsx',
      'operations/SourceBuildsPage.tsx',
      'sources/SourceHealthDetailPage.tsx',
    ]
    for (const relativePath of sourceFiles) {
      expect(read(relativePath)).not.toMatch(/\bfetch\s*\(/)
    }
  })
})
```

- [ ] **Step 2: Run the contract tests and confirm the expected red state**

Run: `npm test -- --run src/architecture/component-boundaries.test.ts`

Expected: FAIL because the five target pages still contain direct `<table>` markup and do not all import `DataTable`.

- [ ] **Step 3: Commit the red test contract**

```bash
git add frontend/src/architecture/component-boundaries.test.ts
git commit -m "test: define frontend component boundary contract"
```

### Task 2: Complete Shared Data and Form/Detail Primitives

**Files:**
- Modify: `frontend/src/components/data/DataTable.tsx`
- Modify: `frontend/src/components/data/DataTable.test.tsx`
- Create: `frontend/src/components/form/FormField.tsx`
- Create: `frontend/src/components/form/FormActions.tsx`
- Create: `frontend/src/components/form/FormField.test.tsx`
- Create: `frontend/src/components/form/FormActions.test.tsx`
- Create: `frontend/src/components/detail/DetailPanel.tsx`
- Create: `frontend/src/components/detail/AttemptTimeline.tsx`
- Create: `frontend/src/components/detail/DetailPanel.test.tsx`
- Create: `frontend/src/components/detail/AttemptTimeline.test.tsx`

- [ ] **Step 1: Add failing primitive behavior tests**

```tsx
test('DataTable renders an accessible empty state without a fake row', () => {
  render(<DataTable rows={[]} columns={[{ id: 'name', header: 'Name', cell: () => null }]} getRowKey={() => 'empty'} emptyLabel="No rows" />)
  expect(screen.getByText('No rows')).toBeInTheDocument()
  expect(screen.queryAllByRole('row')).toHaveLength(2)
})

test('FormField exposes label, help, and error through the control', () => {
  render(<FormField label="Name" htmlFor="name" help="Use a display name" error="Required"><Input id="name" /></FormField>)
  expect(screen.getByLabelText('Name')).toHaveAttribute('aria-describedby', expect.stringContaining('name-help'))
  expect(screen.getByText('Required')).toHaveAttribute('role', 'alert')
})

test('DetailPanel renders an empty state and keyed values', () => {
  const { rerender } = render(<DetailPanel title="Details" emptyLabel="Select a row" />)
  expect(screen.getByText('Select a row')).toBeInTheDocument()
  rerender(<DetailPanel title="Details" items={[{ label: 'Status', value: 'healthy' }]} />)
  expect(screen.getByText('Status')).toBeInTheDocument()
  expect(screen.getByText('healthy')).toBeInTheDocument()
})

test('AttemptTimeline keeps attempt order and status labels', () => {
  render(<AttemptTimeline items={[{ id: 'a1', label: 'Attempt 1', status: 'failed' }, { id: 'a2', label: 'Attempt 2', status: 'passed' }]} />)
  expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Attempt 1failed', 'Attempt 2passed'])
})
```

- [ ] **Step 2: Run the new tests and verify they fail for missing props/modules**

Run: `npm test -- --run src/components/data/DataTable.test.tsx src/components/form/FormField.test.tsx src/components/form/FormActions.test.tsx src/components/detail/DetailPanel.test.tsx src/components/detail/AttemptTimeline.test.tsx`

Expected: FAIL with missing `emptyLabel`, missing form/detail modules, and missing test fixtures.

- [ ] **Step 3: Implement the minimal presentation-only primitives**

`DataTable` receives `emptyLabel?: ReactNode` and renders one `TableRow` with `colSpan={columns.length}` when `rows` is empty. `FormField` generates stable `${htmlFor}-help` and `${htmlFor}-error` IDs, joins them into `aria-describedby`, and renders the error with `role="alert"`. `FormActions` renders a right-aligned flex row and accepts `children`. `DetailPanel` accepts `title`, optional `description`, `items`, `emptyLabel`, and `children`; `AttemptTimeline` accepts `{ id, label, status, detail? }[]` and renders a semantic `<ol>` with `role="listitem"` entries using `StatusBadge`.

```tsx
export interface FormActionsProps { children: ReactNode; className?: string }
export function FormActions({ children, className }: FormActionsProps) {
  return <div className={cn('flex flex-wrap items-center justify-end gap-2', className)}>{children}</div>
}
```

- [ ] **Step 4: Run primitive tests and commit**

Run: `npm test -- --run src/components/data/DataTable.test.tsx src/components/form/FormField.test.tsx src/components/form/FormActions.test.tsx src/components/detail/DetailPanel.test.tsx src/components/detail/AttemptTimeline.test.tsx`

Expected: PASS.

```bash
git add frontend/src/components/data/DataTable.tsx frontend/src/components/data/DataTable.test.tsx frontend/src/components/form frontend/src/components/detail
git commit -m "feat: add shared frontend form and detail primitives"
```

### Task 3: Migrate Operations Tables

**Files:**
- Modify: `frontend/src/features/operations/JobsPage.tsx`
- Modify: `frontend/src/features/operations/ReviewQueuePage.tsx`
- Modify: `frontend/src/features/operations/SourceBuildsPage.tsx`
- Modify: `frontend/src/features/operations/JobsPage.test.tsx`
- Modify: `frontend/src/features/operations/ReviewQueuePage.test.tsx`
- Modify: `frontend/src/features/operations/SourceBuildsPage.test.tsx`
- Test: `frontend/src/architecture/component-boundaries.test.ts`

- [ ] **Step 1: Add behavior assertions for shared table states**

Add to each page test a row assertion plus an empty response assertion that expects the shared empty text, for example:

```tsx
test('jobs page shows the shared empty state when the server returns no jobs', async () => {
  operationsMocks.listOperationsJobs.mockResolvedValueOnce({ data: [], meta: { total: 0 } })
  render(<JobsPage />)
  expect(await screen.findByText('No operations jobs yet')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the page tests and verify the new empty-state cases fail or expose existing direct markup**

Run: `npm test -- --run src/features/operations/JobsPage.test.tsx src/features/operations/ReviewQueuePage.test.tsx src/features/operations/SourceBuildsPage.test.tsx src/architecture/component-boundaries.test.ts`

Expected: the boundary test remains red until migration; each page test identifies its current empty-state output.

- [ ] **Step 3: Replace table JSX with typed `DataTable` columns**

Each page imports `DataTable`, defines a `const columns: DataTableColumn<Row>[]` inside the module, and renders:

```tsx
<DataTable rows={rows} columns={columns} getRowKey={(row) => row.id} emptyLabel={t('No operations jobs yet')} />
```

Keep action callbacks and audit formatting in column `cell` functions. Keep `PaginatedListControls` immediately above the table so pagination remains unchanged.

- [ ] **Step 4: Run operations tests, boundary tests, and commit**

Run: `npm test -- --run src/features/operations/JobsPage.test.tsx src/features/operations/ReviewQueuePage.test.tsx src/features/operations/SourceBuildsPage.test.tsx src/architecture/component-boundaries.test.ts`

Expected: PASS; no target page contains `<table>`.

```bash
git add frontend/src/features/operations frontend/src/architecture/component-boundaries.test.ts
git commit -m "refactor: migrate operations pages to shared data tables"
```

### Task 4: Migrate Event Delivery and Source Health Details

**Files:**
- Modify: `frontend/src/features/operations/EventDeliveriesPage.tsx`
- Modify: `frontend/src/features/operations/EventDeliveriesPage.test.tsx`
- Modify: `frontend/src/features/sources/SourceHealthDetailPage.tsx`
- Modify: `frontend/src/features/sources/SourceHealthDetailPage.test.tsx`
- Modify: `frontend/src/components/data/DataTable.tsx`
- Modify: `frontend/src/components/detail/AttemptTimeline.tsx`

- [ ] **Step 1: Add failing behavior tests for selected rows and health states**

```tsx
test('event deliveries keeps the selected row highlighted through DataTable', async () => {
  render(<EventDeliveriesPage />)
  fireEvent.click(await screen.findByRole('button', { name: /delivery-event/ }))
  expect(screen.getByRole('row', { name: /delivery-event/ })).toHaveClass('bg-muted/30')
})

test('source health detail renders shared loading and empty history states', async () => {
  sourceHealthMocks.getSourceHealth.mockResolvedValueOnce({ data: { runs: [], snapshot: null, route_decision: { policy: 'probe_only', score: 0, reason: 'not_probed' } } })
  render(<MemoryRouter initialEntries={['/sources/health/7']}><Routes><Route path="/sources/health/:sourceId" element={<SourceHealthDetailPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('No probe history')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the focused tests and confirm the expected red assertions**

Run: `npm test -- --run src/features/operations/EventDeliveriesPage.test.tsx src/features/sources/SourceHealthDetailPage.test.tsx`

- [ ] **Step 3: Extend shared primitives and migrate both pages**

Add `getRowClassName?: (row: Row) => string | undefined` to `DataTableProps` and pass it to each `TableRow`. Use `DataTable` for delivery rows and keep the selected event ID in the cell/action closure. Use `DetailPanel` for snapshot/route/request sections and `AttemptTimeline` for probe history. Replace ad hoc loading and empty paragraphs with `LoadingState`, `ErrorState`, and `EmptyState`; use `StatusBadge` instead of local color-only status functions while retaining status text.

```tsx
<DataTable
  rows={deliveries}
  columns={deliveryColumns}
  getRowKey={getDeliveryId}
  getRowClassName={(row) => getDeliveryId(row) === selectedEventId ? 'bg-muted/30' : undefined}
  emptyLabel={t('No event deliveries yet')}
/>
<DetailPanel title="Route decision" items={routeItems} />
<AttemptTimeline items={attempts.map((attempt) => ({
  id: attempt.id,
  label: `Attempt ${getAttemptNumber(attempt)}`,
  status: attempt.delivered ? 'delivered' : 'failed',
  detail: getAttemptError(attempt) ?? 'No error payload',
}))} />
```

- [ ] **Step 4: Run focused tests and commit**

Run: `npm test -- --run src/features/operations/EventDeliveriesPage.test.tsx src/features/sources/SourceHealthDetailPage.test.tsx src/components/data/DataTable.test.tsx src/components/detail/DetailPanel.test.tsx src/components/detail/AttemptTimeline.test.tsx src/architecture/component-boundaries.test.ts`

Expected: PASS.

```bash
git add frontend/src/features/operations/EventDeliveriesPage.tsx frontend/src/features/operations/EventDeliveriesPage.test.tsx frontend/src/features/sources/SourceHealthDetailPage.tsx frontend/src/features/sources/SourceHealthDetailPage.test.tsx frontend/src/components/data/DataTable.tsx frontend/src/components/detail/AttemptTimeline.tsx
git commit -m "refactor: unify delivery and health detail views"
```

### Task 5: Migrate Administrative and Content Forms

**Files:**
- Modify: `frontend/src/features/admin/AdminUsersPage.tsx`
- Modify: `frontend/src/features/admin/ApiKeysPage.tsx`
- Modify: `frontend/src/features/admin/AdminAuditPage.tsx`
- Modify: `frontend/src/features/ai/AIWorkspacePage.tsx`
- Modify: `frontend/src/features/ai/AITasksPage.tsx`
- Modify: `frontend/src/features/translation/TranslationJobsPage.tsx`
- Modify: `frontend/src/features/novel/NovelTasksPage.tsx`
- Modify: `frontend/src/features/novel-analysis/WorkAnalysisPage.tsx`
- Modify: `frontend/src/features/admin/AdminUsersPage.test.tsx`
- Create: `frontend/src/features/admin/ApiKeysPage.test.tsx`
- Create: `frontend/src/features/admin/AdminAuditPage.test.tsx`
- Modify: `frontend/src/features/ai/AIWorkspacePage.test.tsx`
- Create: `frontend/src/features/ai/AITasksPage.test.tsx`
- Create: `frontend/src/features/translation/TranslationJobsPage.test.tsx`
- Create: `frontend/src/features/novel/NovelTasksPage.test.tsx`
- Modify: `frontend/src/features/novel-analysis/WorkAnalysisPage.test.tsx`

- [ ] **Step 1: Add failing tests for shared form field semantics and detail empty states**

```tsx
test('admin user form exposes shared field descriptions and errors', async () => {
  render(<AdminUsersPage />)
  const username = await screen.findByLabelText('Username')
  expect(username).toHaveAttribute('aria-describedby', expect.stringContaining('username-help'))
})
```

Add these concrete assertions:

```tsx
test('api key form exposes its shared field description', async () => {
  render(<ApiKeysPage />)
  expect(await screen.findByLabelText('API key name')).toHaveAttribute('aria-describedby', expect.stringContaining('api-key-name-help'))
})

test('AI workspace composer is labelled through the shared field wrapper', () => {
  render(<AIWorkspacePage />)
  expect(screen.getByLabelText('Message')).toHaveAttribute('aria-describedby', expect.stringContaining('message-help'))
})

test('work analysis renders the shared empty evidence panel', async () => {
  novelAnalysisMocks.getWorkSnapshot.mockResolvedValueOnce({ data: { published_claims: [], candidate_claims: [], open_conflicts: [] } })
  render(<WorkAnalysisPage />)
  expect(await screen.findByText('No evidence selected')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run focused tests and verify the new semantics fail**

Run: `npm test -- --run src/features/admin/AdminUsersPage.test.tsx src/features/ai/AIWorkspacePage.test.tsx src/features/novel-analysis/WorkAnalysisPage.test.tsx`

- [ ] **Step 3: Wrap repeated labels and actions with `FormField` and `FormActions`**

Replace repeated label/help/error groups with:

```tsx
<FormField label="Username" htmlFor="username" help="用于登录控制台">
  <Input id="username" value={draft.username} onChange={handleUsernameChange} />
</FormField>
<FormActions>
  <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
</FormActions>
```

Use `DetailPanel` and `StatusBadge` for selected AI/novel/translation details without moving API calls into shared components.

- [ ] **Step 4: Run all migrated page tests and commit**

Run: `npm test -- --run src/features/admin src/features/ai src/features/translation src/features/novel src/features/novel-analysis`

Expected: PASS.

```bash
git add frontend/src/features/admin frontend/src/features/ai frontend/src/features/translation frontend/src/features/novel frontend/src/features/novel-analysis
git commit -m "refactor: standardize admin and content forms"
```

### Task 6: Migrate System Settings and Remove Layout Alias Usage

**Files:**
- Create: `frontend/src/components/layout/SettingsTabs.tsx`
- Create: `frontend/src/components/layout/SettingsTabs.test.tsx`
- Modify: `frontend/src/features/system/SystemSettingsLayout.tsx`
- Delete: `frontend/src/features/system/SettingsTabs.tsx` after its imports migrate
- Modify: `frontend/src/features/system/ProviderRoutingSettings.tsx`
- Modify: `frontend/src/features/system/AgentGovernanceSettings.tsx`
- Modify: `frontend/src/features/system/AgentAutomationSettings.tsx`
- Modify: `frontend/src/features/system/AgentBudgetSettings.tsx`
- Modify: `frontend/src/features/system/AgentOverviewSettings.tsx`
- Modify: `frontend/src/features/system/AgentRoleSettings.tsx`
- Modify: `frontend/src/features/system/AgentAuditSettings.tsx`
- Modify: `frontend/src/features/admin/AdminAuditPage.tsx`
- Modify: `frontend/src/features/admin/AdminUsersPage.tsx`
- Modify: `frontend/src/features/admin/ApiKeysPage.tsx`
- Modify: `frontend/src/features/ai/AITasksPage.tsx`
- Modify: `frontend/src/features/ai/AIWorkspacePage.tsx`
- Modify: `frontend/src/features/engine/EngineRunsPage.tsx`
- Modify: `frontend/src/features/novel-analysis/WorkAnalysisPage.tsx`
- Modify: `frontend/src/features/novel/NovelTasksPage.tsx`
- Modify: `frontend/src/features/operations/EventDeliveriesPage.tsx`
- Modify: `frontend/src/features/operations/JobsPage.tsx`
- Modify: `frontend/src/features/operations/ReviewQueuePage.tsx`
- Modify: `frontend/src/features/operations/SourceBuildsPage.tsx`
- Modify: `frontend/src/features/sources/SourceHealthDetailPage.tsx`
- Modify: `frontend/src/features/sources/SourceHealthPage.tsx`
- Modify: `frontend/src/features/sources/SourceRuleEditorPage.tsx`
- Modify: `frontend/src/features/system/SystemSettingsPage.tsx`
- Modify: `frontend/src/features/translation/TranslationJobsPage.tsx`

- [ ] **Step 1: Add failing tests for layout and settings navigation contracts**

```tsx
test('settings tabs accepts registry definitions without importing a feature module', () => {
  render(
    <SettingsTabs
      allTabs={[{ id: 'agents/governance', label: 'Governance' }]}
      selectedPath="agents/governance"
      settingsPath={(path) => `/settings/${path}`}
    />,
  )
  expect(screen.getByRole('tab', { name: 'Governance' })).toBeInTheDocument()
})
```

Add a source-contract assertion that production pages import `ConsolePageShell` directly and that `ConsoleLayout.tsx` has no production importers.

```tsx
test('authenticated console pages use the canonical shell', () => {
  const pageFiles = [
    'admin/AdminUsersPage.tsx', 'admin/ApiKeysPage.tsx', 'ai/AITasksPage.tsx',
    'engine/EngineRunsPage.tsx', 'operations/JobsPage.tsx',
    'operations/ReviewQueuePage.tsx', 'sources/SourceHealthPage.tsx',
    'system/SystemSettingsPage.tsx', 'translation/TranslationJobsPage.tsx',
  ]
  for (const relativePath of pageFiles) {
    const source = read(relativePath)
    expect(source).toContain("@/components/layout/ConsolePageShell")
    expect(source).not.toContain("@/components/layout/ConsoleLayout")
  }
  expect(readFileSync(resolve(process.cwd(), 'src/components/layout/ConsoleLayout.tsx'), 'utf8')).toContain('ConsolePageShell')
})
```

- [ ] **Step 2: Run the settings/layout tests and verify they fail**

Run: `npm test -- --run src/features/system/SystemSettingsLayout.test.tsx src/features/system/AgentGovernanceSettings.test.tsx src/components/layout/SettingsTabs.test.tsx src/architecture/component-boundaries.test.ts`

- [ ] **Step 3: Move the settings tab presentation and migrate all page-shell imports**

Make `components/layout/SettingsTabs.tsx` accept only `allTabs: { id: string; label: ReactNode }[]`, `selectedPath: string`, and `settingsPath: (id: string) => string`. Keep `settingsRegistry.ts` in `features/system`. Update `SystemSettingsLayout` to map the registry into those props and replace every listed `ConsoleLayout` import with `ConsolePageShell`.

- [ ] **Step 4: Run the complete system settings suite and commit**

Run: `npm test -- --run src/features/system src/components/layout`

Expected: PASS with no production imports of `ConsoleLayout`.

```bash
git add frontend/src/components/layout frontend/src/features/system frontend/src/features
git commit -m "refactor: unify settings and console page shells"
```

### Task 7: Boundary, Accessibility, and Full Regression Verification

**Files:**
- Modify: `frontend/src/architecture/component-boundaries.test.ts`
- Modify: component/page tests touched by migration
- Remove: `frontend/src/components/layout/ConsoleLayout.tsx` after the import-contract test is green

- [ ] **Step 1: Add final source-boundary assertions**

```tsx
test('feature pages do not own duplicated list-state markup', () => {
  const listPages = [
    'operations/JobsPage.tsx',
    'operations/ReviewQueuePage.tsx',
    'operations/EventDeliveriesPage.tsx',
    'operations/SourceBuildsPage.tsx',
    'sources/SourceHealthDetailPage.tsx',
  ]
  for (const relativePath of listPages) {
    const source = readFileSync(resolve(featureRoot, relativePath), 'utf8')
    expect(source).not.toMatch(/<table\b/)
    expect(source).toContain('PaginatedListControls')
  }
})
```

- [ ] **Step 2: Run all frontend tests and inspect accessibility failures**

Run: `npm test -- --run`

Expected: all test files pass; no missing accessible names, duplicate IDs, or unhandled async state warnings.

- [ ] **Step 3: Run production checks**

Run: `npm run build` and `git diff --check`

Expected: TypeScript/Vite build succeeds and the diff has no whitespace errors.

- [ ] **Step 4: Verify no direct transport calls remain in feature pages**

Run: `rg -n "\b(fetch|axios)\s*\(" frontend/src/features --glob '*.tsx'`

Expected: no output.

- [ ] **Step 5: Commit and push the completed migration**

```bash
git add frontend/src docs/superpowers/plans/2026-07-19-frontend-component-system.md
git commit -m "refactor: complete frontend component system migration"
git push origin main
```
