import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

vi.mock('@/api/modules/operations', () => ({
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

import { JobsPage } from './JobsPage'

test('jobs page shows queued job status and kind', async () => {
  render(<JobsPage />)

  expect(await screen.findByRole('heading', { name: 'Jobs control plane' })).toBeInTheDocument()
  expect(screen.getByText('crawl.refresh')).toBeInTheDocument()
  expect(screen.getByText('queued')).toBeInTheDocument()
})
