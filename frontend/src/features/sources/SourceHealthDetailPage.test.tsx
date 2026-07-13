import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

vi.mock('@/api/modules/sourceHealth', () => ({
  getSourceHealth: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      snapshot: {
        source_id: 67,
        source_name: 'Hetu',
        source_url: 'https://example.test',
        health_status: 'blocked',
        search_status: 'failed',
        toc_status: 'skipped',
        content_status: 'skipped',
        failure_reason: 'waf_blocked',
        route_policy: 'skip',
        route_score: 0,
      },
      route_decision: { policy: 'skip', score: 0, reason: 'waf_blocked' },
      runs: [
        {
          id: 'run-1',
          source_id: 67,
          keyword: 'sample',
          overall_status: 'blocked',
          failure_reason: 'waf_blocked',
          created_at: '2026-07-10T10:00:00+00:00',
          search_result: {
            status: 'failed',
            request_preview: 'https://example.test/search',
            detail: { http_status: 403, response_kind: 'html', response_preview: '<html>challenge</html>' },
          },
          toc_result: { status: 'skipped', detail: {} },
          content_result: { status: 'skipped', detail: {} },
          summary: { route_policy: 'skip', route_score: 0 },
        },
      ],
      failure_timeline: [
        {
          at: '2026-07-10T10:00:00+00:00',
          stage: 'search',
          status: 'failed',
          reason: 'waf_blocked',
          message: '',
          request_preview: 'https://example.test/search',
          http_status: 403,
          response_kind: 'html',
        },
      ],
    },
    meta: {},
    trace_id: null,
  }),
}))

import { SourceHealthDetailPage } from './SourceHealthDetailPage'

test('source health detail renders route decision and probe diagnostics', async () => {
  render(
    <MemoryRouter initialEntries={['/sources/health/67']}>
      <Routes>
        <Route path="/sources/health/:sourceId" element={<SourceHealthDetailPage />} />
      </Routes>
    </MemoryRouter>
  )

  expect(await screen.findByText('Route decision')).toBeInTheDocument()
  expect(screen.getAllByText('waf_blocked').length).toBeGreaterThan(0)
  expect(screen.getByText('Failure timeline')).toBeInTheDocument()
  expect(screen.getByText('https://example.test/search')).toBeInTheDocument()
})
