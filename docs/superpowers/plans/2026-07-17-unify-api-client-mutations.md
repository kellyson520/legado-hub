# Unify API Client Mutation Methods Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the shared frontend API client with envelope-aware `patch` and `delete` methods, migrate the remaining raw mutation calls, and remove redundant system-module casts.

**Architecture:** `createApiClient` remains the only place that owns Axios interceptors and response-envelope unwrapping. API modules will call `apiClient.patch/delete` just like `get/post/put`; no module will manually access `apiClient.raw` for ordinary JSON mutations. Existing API return shapes stay unchanged.

**Tech Stack:** TypeScript 5, Axios, React frontend, Vitest, Vite.

---

### Task 1: Add failing tests for shared mutation unwrapping

**Files:**
- Modify: `frontend/src/api/client.test.tsx`

- [ ] **Step 1: Add a patch/delete envelope test**

Append:

```tsx
test('client unwraps patch and delete envelopes through shared methods', async () => {
  const calls: string[] = []
  const client = createApiClient({
    adapter: async (config) => {
      calls.push(`${config.method}:${config.url}`)
      return {
        data: {
          success: true,
          code: 'OK',
          message: 'ok',
          data: { id: 'row-1' },
          meta: {},
          trace_id: null,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    },
  })

  const patched = await client.patch<{ id: string }>('/api/items/row-1', { enabled: true })
  const deleted = await client.delete<{ id: string }>('/api/items/row-1')

  expect(patched.data.id).toBe('row-1')
  expect(deleted.data.id).toBe('row-1')
  expect(calls).toEqual(['patch:/api/items/row-1', 'delete:/api/items/row-1'])
})
```

- [ ] **Step 2: Run the test before implementation**

```bash
npm exec vitest run src/api/client.test.tsx
```

Expected: FAIL because `createApiClient()` currently has no `patch` or `delete` methods.

### Task 2: Implement envelope-aware patch/delete methods

**Files:**
- Modify: `frontend/src/api/client.ts:75-90`

- [ ] **Step 1: Add `patch` beside `post` and `put`**

Add:

```ts
patch: async <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
  unwrapResponse<T>(await instance.patch<ApiEnvelope<T>>(url, data, config)),
```

- [ ] **Step 2: Add `delete` with Axios request config**

Add:

```ts
delete: async <T>(url: string, config?: AxiosRequestConfig) =>
  unwrapResponse<T>(await instance.delete<ApiEnvelope<T>>(url, config)),
```

Keep the existing request/response interceptors untouched so refresh and authorization behavior remains shared.

- [ ] **Step 3: Run the client tests**

```bash
npm exec vitest run src/api/client.test.tsx
```

Expected: all client tests pass, including the new patch/delete test.

### Task 3: Migrate API modules to the shared mutation contract

**Files:**
- Modify: `frontend/src/api/modules/admin.ts:1-48`
- Modify: `frontend/src/api/modules/interactiveBrowser.ts:1-32`
- Modify: `frontend/src/api/modules/system.ts:90-150`

- [ ] **Step 1: Replace raw admin mutations**

Use the shared methods:

```ts
export function updateUser(id: string, payload: Partial<Pick<AdminUserRow, 'display_name' | 'role'>>): Promise<ApiEnvelope<AdminUserRow>> {
  return apiClient.patch<AdminUserRow>(`/admin/users/${id}`, payload)
}

export function disableApiKey(id: number): Promise<ApiEnvelope<{ api_key_id: number }>> {
  return apiClient.patch<{ api_key_id: number }>(`/admin/api-keys/${id}/disable`)
}

export function deleteApiKey(id: number): Promise<ApiEnvelope<{ api_key_id: number }>> {
  return apiClient.delete<{ api_key_id: number }>(`/admin/api-keys/${id}`)
}
```

Remove only the now-unneeded `.raw` calls; preserve endpoint paths and return envelopes.

- [ ] **Step 2: Replace the raw interactive-browser delete**

Use:

```ts
export function cancelInteractiveBrowserSession(sessionId: string): Promise<ApiEnvelope<InteractiveBrowserSession>> {
  return apiClient.delete<InteractiveBrowserSession>(`/interactive-browser/sessions/${sessionId}`)
}
```

- [ ] **Step 3: Remove redundant system casts**

Keep explicit return types but return the shared client result directly:

```ts
export function listProviders(): Promise<ApiEnvelope<ProviderRow[]>> {
  return apiClient.get<ProviderRow[]>('/system/providers')
}

export function listQuotaPolicies(): Promise<ApiEnvelope<QuotaPolicyRow[]>> {
  return apiClient.get<QuotaPolicyRow[]>('/system/quotas')
}
```

- [ ] **Step 4: Verify no ordinary module uses the raw client**

```bash
rg -n "apiClient\\.raw" frontend/src/api/modules || true
```

Expected: no matches.

### Task 4: Run verification and commit

**Files:**
- No additional source files.

- [ ] **Step 1: Run API and affected feature tests**

```bash
npm exec vitest run \
  src/api/client.test.tsx \
  src/api/types.test.ts \
  src/features/admin/AdminUsersPage.test.tsx \
  src/features/system/ProviderRoutingSettings.test.tsx \
  src/features/operations/ManualVerificationPanel.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 2: Type-check and build**

```bash
npm run build
```

Expected: TypeScript and Vite both exit with code 0.

- [ ] **Step 3: Check, review, and commit**

```bash
git diff --check
git status --short
git add frontend/src/api/client.ts frontend/src/api/client.test.tsx frontend/src/api/modules/admin.ts frontend/src/api/modules/interactiveBrowser.ts frontend/src/api/modules/system.ts docs/superpowers/plans/2026-07-17-unify-api-client-mutations.md
git commit -m "refactor: unify api client mutation methods"
```

Expected: one focused commit with no raw mutation calls left in API modules.
