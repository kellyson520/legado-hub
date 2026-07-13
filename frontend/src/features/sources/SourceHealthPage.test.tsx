import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

vi.mock('@/api/modules/sourceHealth', () => ({
  listSourceHealth: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        source_id: 7,
        source_name: '七猫小说',
        source_url: 'https://www.qimao.com',
        health_status: 'healthy',
        search_status: 'ok',
        toc_status: 'ok',
        content_status: 'ok',
        failure_reason: '',
        route_policy: 'allow',
      },
      {
        source_id: 4,
        source_name: '起点读书限免+本章说',
        source_url: 'https://www.qidian.com',
        health_status: 'blocked',
        search_status: 'failed',
        toc_status: 'skipped',
        content_status: 'skipped',
        failure_reason: 'token_missing',
        route_policy: 'skip',
      },
    ],
    meta: { page: 1, page_size: 20, total: 2 },
    trace_id: null,
  }),
  probeSourceHealth: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {},
    meta: {},
    trace_id: null,
  }),
  recoverSourceHealth: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {},
    meta: {},
    trace_id: null,
  }),
}))

import { SourceHealthPage } from './SourceHealthPage'

test('source health page shows stage statuses and failure reasons', async () => {
  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('Source health control plane')).toBeInTheDocument()
  expect(await screen.findByText('token_missing')).toBeInTheDocument()
  expect(await screen.findByText('Probe now')).toBeInTheDocument()
  expect(
    (await screen.findAllByRole('link', { name: 'View source details' })).find(
      (link) => link.getAttribute('href') === '/sources/health/7'
    )
  ).toBeDefined()
})
