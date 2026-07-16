import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

const engineMocks = vi.hoisted(() => ({
  listEngineRuns: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 'run-1',
        source_version_id: 'ver-1',
        grade: 'A',
        step_results: {
          search: { passed: true, elapsed_ms: 120 },
          toc: { passed: true, elapsed_ms: 240 },
        },
      },
    ],
    meta: { total: 1 },
    trace_id: null,
  }),
  listEngineDeployments: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 'dep-1',
        source_version_id: 'ver-1',
        status: 'published',
        action: 'deploy',
      },
    ],
    meta: { total: 1 },
    trace_id: null,
  }),
  listEngineSourceBuilds: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 'source-version-1',
        source_id: 'https://console.test/books',
        status: 'candidate',
        payload: {
          keyword: 'sample',
          autonomous_build: {
            decision: 'canary',
            strategy: 'deterministic_patch',
            validation: { grade: 'A', quality_score: 96 },
            probe: { search_status: 'ok', toc_status: 'ok', content_status: 'ok' },
          },
          source_rule: { bookSourceName: 'Console Test' },
        },
        created_by: 'console:1',
      },
    ],
    meta: { total: 1 },
    trace_id: null,
  }),
  submitEngineSourceBuild: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'accepted',
    data: {
      job_id: 'job-1',
      normalized_url: 'https://new.test/books',
      source_version_id: 'source-version-2',
      source_version_status: 'candidate',
      status: 'candidate',
    },
    meta: {},
    trace_id: null,
  }),
  testEngineRegex: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      match_count: 1,
      matches: [{ match: '第12章', groups: ['12'], span: [0, 4] }],
      replacement_preview: '章节12：开始',
      error: null,
    },
    meta: {},
    trace_id: null,
  }),
}))

const statusMocks = vi.hoisted(() => ({
  ListStatus: vi.fn((props: { loading: boolean; empty: boolean }) => {
    void props
    return null
  }),
}))

vi.mock('@/api/modules/engine', () => ({
  listEngineRuns: engineMocks.listEngineRuns,
  listEngineDeployments: engineMocks.listEngineDeployments,
  listEngineSourceBuilds: engineMocks.listEngineSourceBuilds,
  submitEngineSourceBuild: engineMocks.submitEngineSourceBuild,
  testEngineRegex: engineMocks.testEngineRegex,
}))
vi.mock('@/components/data/ListStatus', () => statusMocks)

vi.mock('@/api/modules/admin', () => ({
  listUsers: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{ id: '1', username: 'admin', roles: ['super_admin'] }],
    meta: { total: 1 },
    trace_id: null,
  }),
  listAuditLogs: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [],
    meta: { total: 0 },
    trace_id: null,
  }),
}))

import { AuthProvider } from '@/app/providers/AuthProvider'
import { AdminUsersPage } from '@/features/admin/AdminUsersPage'
import { EngineRunsPage } from './EngineRunsPage'

test('engine runs page shows step timeline and deployment decision', async () => {
  render(<EngineRunsPage />)

  expect(await screen.findByText('Rule writing studio')).toBeInTheDocument()
  expect(screen.getByText('https://console.test/books')).toBeInTheDocument()
  expect(screen.getByText('validation A / 96')).toBeInTheDocument()
  expect(statusMocks.ListStatus.mock.calls.some(([props]) => props.loading === false && props.empty === false)).toBe(true)
  expect(await screen.findByText('search')).toBeInTheDocument()
  expect(await screen.findByText('deployment decision')).toBeInTheDocument()
})

test('engine rule center tests regex and marks verification wall as blocked', async () => {
  engineMocks.listEngineSourceBuilds.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{
      id: 'blocked-version',
      source_id: 'https://blocked.test/books',
      status: 'candidate',
      payload: { autonomous_build: { probe: { content_status: 'verification_wall' } } },
    }],
    meta: { total: 1 },
    trace_id: null,
  })
  render(<EngineRunsPage />)

  fireEvent.click(screen.getByRole('button', { name: '测试正则' }))

  await waitFor(() => {
    expect(engineMocks.testEngineRegex).toHaveBeenCalledWith({
      text: '第12章：开始',
      pattern: '第(\\d+)章',
      replacement: '章节$1',
    })
  })
  expect(await screen.findByText(/替换预览：章节12：开始/)).toBeInTheDocument()
  expect(await screen.findByText('正文访问受阻')).toBeInTheDocument()
  expect(screen.getByText('不可发布')).toBeInTheDocument()
})

test('engine rule writing form submits a console source build job', async () => {
  render(<EngineRunsPage />)

  fireEvent.change(await screen.findByLabelText('Source URL'), {
    target: { value: 'https://new.test/books/' },
  })
  fireEvent.change(screen.getByLabelText('Keyword'), {
    target: { value: 'sample' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Start source build' }))

  await waitFor(() => {
    expect(engineMocks.submitEngineSourceBuild).toHaveBeenCalledWith({
      url: 'https://new.test/books/',
      keyword: 'sample',
    })
  })
  expect(await screen.findByText('Queued job job-1')).toBeInTheDocument()
})

test('admin users page hides destructive actions without permission', async () => {
  render(
    <AuthProvider
      bootstrapSession={{
        accessToken: 'token',
        refreshToken: 'refresh',
        user: { id: '1', username: 'operator', permissions: ['users.read'] },
      }}
    >
      <AdminUsersPage />
    </AuthProvider>
  )

  expect(await screen.findByText('admin')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /delete user/i })).not.toBeInTheDocument()
})
