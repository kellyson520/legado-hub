import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

const operationsMocks = vi.hoisted(() => ({
  listOperationsJobs: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 'job-1',
        kind: 'crawl.refresh',
        status: 'queued',
        tenantId: 'tenant-console',
        attemptCount: 1,
        createdAt: '2026-07-11T10:00:00Z',
      },
    ],
    meta: { total: 1 },
    trace_id: null,
  }),
}))

vi.mock('@/api/modules/operations', () => operationsMocks)

import { JobsPage } from './JobsPage'

test('jobs page shows queued job status and kind', async () => {
  render(<JobsPage />)

  expect(await screen.findByRole('heading', { name: '任务控制台' })).toBeInTheDocument()
  expect(screen.getByText('crawl.refresh')).toBeInTheDocument()
  expect(screen.getByText('排队中')).toBeInTheDocument()
})

test('jobs page shows the shared empty state when the server returns no jobs', async () => {
  operationsMocks.listOperationsJobs.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [],
    meta: { total: 0 },
    trace_id: null,
  })

  render(<JobsPage />)

  expect(await screen.findByText('暂无运营任务')).toBeInTheDocument()
})
