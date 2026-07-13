# New API 风格控制台壳层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Legado Hub 提供带权限导航、响应式侧边栏及三模式主题的统一管理控制台。

**Architecture:** 新增 `ThemeProvider` 管理持久化主题模式和根节点 class；新增单一 `navigation` 配置描述可访问菜单。`AppShell` 根据登录路由决定是否加载控制台壳层，`ConsoleLayout` 只负责业务页面标题和主体内容。

**Tech Stack:** React 18、React Router 6、TypeScript、Tailwind CSS、Vitest、Testing Library、lucide-react。

---

## Sync Status (2026-07-11)

> Sync note: 下方 checkbox 保留原始实施脚本；当前执行状态以本节为准。

- **Overall:** 代码已落地，自动化验证通过；仅 Task 4 中“浏览器登录/主题/窄屏抽屉”的人工走查未在本次同步中完整复验。
- **Verification:**
  - `npm test -- --run src/app/providers/ThemeProvider.test.tsx src/components/layout/AppConsoleShell.test.tsx src/features/sources/SourceListPage.test.tsx src/features/sources/SourceHealthPage.test.tsx src/features/sources/SourceHealthDetailPage.test.tsx src/features/engine/EngineRunsPage.test.tsx src/features/system/SystemSettingsPage.test.tsx src/features/auth/LoginPage.test.tsx src/app/router/guards.test.tsx` → `9 files, 14 tests passed`
  - `npm run build` → pass
  - `npm run dev -- --host 127.0.0.1 --port 5173` + `Invoke-WebRequest http://127.0.0.1:5173/login -UseBasicParsing` → `200`

| Task | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Task 1 | 完成 | `ThemeProvider.test.tsx` 通过 | `ThemeProvider`、`main.tsx`、`index.css` 已接入三模式主题。 |
| Task 2 | 完成 | `AppConsoleShell.test.tsx` 通过 | 权限导航、响应式 shell、breadcrumb、主题切换已落地。 |
| Task 3 | 完成 | `SourceListPage` / `SourceHealthPage` / `SourceHealthDetailPage` / `EngineRunsPage` / `SystemSettingsPage` 测试通过 | 紧凑布局与共享控件已扩散到计划覆盖页面。 |
| Task 4 | 完成（待人工走查补齐） | `LoginPage.test.tsx`、`guards.test.tsx` 通过，`/login` 返回 `200` | 登录页主题化与 `/login` 壳层隔离已完成；人工登录与窄屏抽屉回归未在本次同步中复测。 |

### Task 1: Theme State and Tokens

**Files:**
- Create: `frontend/src/app/providers/ThemeProvider.tsx`
- Create: `frontend/src/app/providers/ThemeProvider.test.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Write the failing theme test**

```tsx
test('persists a selected theme mode and applies its resolved class', async () => {
  render(<ThemeProvider><ThemeProbe /></ThemeProvider>)
  await userEvent.click(screen.getByRole('button', { name: 'Set light' }))
  expect(document.documentElement).toHaveClass('light')
  expect(window.localStorage.getItem('legado.theme-mode')).toBe('light')
})
```

- [ ] **Step 2: Run the theme test to verify RED**

Run: `npm test -- --run src/app/providers/ThemeProvider.test.tsx`

Expected: FAIL because `ThemeProvider` and `ThemeProbe` do not exist.

- [ ] **Step 3: Implement the provider and semantic tokens**

```tsx
export type ThemeMode = 'light' | 'dark' | 'system'
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(readStoredTheme)
  const resolved = resolveTheme(mode)
  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolved === 'dark')
    document.documentElement.classList.toggle('light', resolved === 'light')
    localStorage.setItem('legado.theme-mode', mode)
  }, [mode, resolved])
  return <ThemeContext.Provider value={{ mode, resolved, setMode }}>{children}</ThemeContext.Provider>
}
```

Add deep and light semantic CSS variables to `index.css`; use the existing Tailwind `dark` class strategy. Wrap `AuthProvider` and `AppShell` in `ThemeProvider` from `main.tsx`.

- [ ] **Step 4: Run the theme test to verify GREEN**

Run: `npm test -- --run src/app/providers/ThemeProvider.test.tsx`

Expected: PASS.

### Task 2: Permission-Aware Navigation and Responsive Shell

**Files:**
- Create: `frontend/src/app/navigation.tsx`
- Create: `frontend/src/components/layout/AppConsoleShell.tsx`
- Create: `frontend/src/components/layout/AppConsoleShell.test.tsx`
- Modify: `frontend/src/app/AppShell.tsx`
- Modify: `frontend/src/app/router.tsx`

- [ ] **Step 1: Write failing shell tests**

```tsx
test('shows only navigation entries allowed by the current session', () => {
  renderShell(['book_sources.read'])
  expect(screen.getByRole('link', { name: '书源' })).toBeVisible()
  expect(screen.queryByRole('link', { name: '用户管理' })).not.toBeInTheDocument()
})

test('opens and closes the mobile navigation drawer', async () => {
  renderShell(['book_sources.read'])
  await userEvent.click(screen.getByRole('button', { name: '打开导航' }))
  expect(screen.getByRole('navigation', { name: '主导航' })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: '关闭导航' }))
  expect(screen.queryByRole('dialog', { name: '导航菜单' })).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the shell tests to verify RED**

Run: `npm test -- --run src/components/layout/AppConsoleShell.test.tsx`

Expected: FAIL because `AppConsoleShell` and navigation configuration do not exist.

- [ ] **Step 3: Implement navigation config and shell**

```tsx
export const navigationGroups = [
  { label: '资源', items: [{ label: '书源', to: '/sources', icon: BookOpen, permission: 'book_sources.read' }] },
  { label: '运营', items: [{ label: '规则引擎', to: '/engine', icon: Workflow, permission: 'engine.test' }] },
  { label: '管理', items: [{ label: '用户管理', to: '/admin/users', icon: Users, permission: 'users.read' }] },
] as const
```

Render group headings, active `NavLink` styles, desktop collapse control, a mobile dialog drawer, service status, breadcrumb, theme segmented control, and account/logout control. Filter items using `useAuth().hasPermission`. Make `AppShell` return the raw child tree only for `/login`; all other routes render within `AppConsoleShell`. Derive the breadcrumb from the navigation config, without duplicating route permissions.

- [ ] **Step 4: Run the shell tests to verify GREEN**

Run: `npm test -- --run src/components/layout/AppConsoleShell.test.tsx`

Expected: PASS.

### Task 3: Compact Content Components and Page Integration

**Files:**
- Modify: `frontend/src/components/layout/ConsoleLayout.tsx`
- Modify: `frontend/src/components/ui/button.tsx`
- Modify: `frontend/src/components/ui/card.tsx`
- Modify: `frontend/src/components/ui/table.tsx`
- Modify: `frontend/src/features/sources/SourceListPage.tsx`
- Modify: `frontend/src/features/sources/SourceHealthPage.tsx`
- Modify: `frontend/src/features/sources/SourceHealthDetailPage.tsx`
- Modify: `frontend/src/features/engine/EngineRunsPage.tsx`
- Modify: `frontend/src/features/admin/AdminUsersPage.tsx`
- Modify: `frontend/src/features/admin/AdminAuditPage.tsx`
- Modify: `frontend/src/features/ai/AITasksPage.tsx`
- Modify: `frontend/src/features/translation/TranslationJobsPage.tsx`
- Modify: `frontend/src/features/novel/NovelTasksPage.tsx`
- Modify: `frontend/src/features/system/SystemSettingsPage.tsx`
- Test: `frontend/src/features/sources/SourceListPage.test.tsx`

- [ ] **Step 1: Extend the source-page test before changing its layout**

```tsx
expect(await screen.findByRole('heading', { name: 'Runtime source inventory' })).toBeVisible()
expect(screen.getByRole('link', { name: 'Open source health control plane' })).toHaveClass('inline-flex')
```

- [ ] **Step 2: Run the source-page test to verify RED**

Run: `npm test -- --run src/features/sources/SourceListPage.test.tsx`

Expected: FAIL because the source action is not the standardized compact action control.

- [ ] **Step 3: Apply the shared compact treatment**

```tsx
export function ConsoleLayout({ eyebrow, title, description, actions, children }: ConsoleLayoutProps) {
  return <section className="mx-auto w-full max-w-[1440px] space-y-5 px-4 py-5 lg:px-8">
    <header className="flex flex-col gap-4 border-b border-border pb-5 md:flex-row md:items-end md:justify-between">
      <div><p className="text-xs font-medium text-muted-foreground">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>{children}
  </section>
}
```

Replace oversized translucent page cards and ad-hoc pill actions in all listed feature pages with shared `Card`, `Button`, table, status and `ConsoleLayout` styles. Keep every existing label, handler, link target, loading state and data request unchanged. Use icon-only buttons only when an accessible label and tooltip title are present.

- [ ] **Step 4: Run the focused page tests to verify GREEN**

Run: `npm test -- --run src/features/sources/SourceListPage.test.tsx src/features/sources/SourceHealthPage.test.tsx src/features/sources/SourceHealthDetailPage.test.tsx src/features/engine/EngineRunsPage.test.tsx src/features/system/SystemSettingsPage.test.tsx`

Expected: PASS.

### Task 4: Login Surface and Regression Verification

**Files:**
- Modify: `frontend/src/features/auth/LoginPage.tsx`
- Modify: `frontend/src/features/auth/LoginPage.test.tsx`
- Modify: `frontend/src/app/router/guards.test.tsx`

- [ ] **Step 1: Write the failing login presentation test**

```tsx
expect(screen.getByText('Legado Hub')).toBeVisible()
expect(screen.getByRole('button', { name: 'Sign in' })).toHaveClass('bg-primary')
```

- [ ] **Step 2: Run the login test to verify RED**

Run: `npm test -- --run src/features/auth/LoginPage.test.tsx`

Expected: FAIL because the login page has the old hard-coded dark visual shell.

- [ ] **Step 3: Implement login theme integration**

Keep form behavior unchanged. Replace hard-coded colors with semantic tokens, compact card treatment and product identity consistent with the console. Do not render the authenticated application sidebar on `/login`.

- [ ] **Step 4: Run the full frontend verification**

Run: `npm test -- --run && npm run build`

Expected: all Vitest suites PASS and TypeScript/Vite build exits with code 0.

- [ ] **Step 5: Check the live application**

Run: `Invoke-WebRequest http://127.0.0.1:5173/login -UseBasicParsing | Select-Object -ExpandProperty StatusCode`

Expected: `200`. In a browser, authenticate using `admin/admin`, test each theme, navigate a permitted item, and resize to a narrow viewport to verify the drawer.
