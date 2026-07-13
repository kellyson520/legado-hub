import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

const operationsMocks = vi.hoisted(() => ({
  listSourceBuildCandidates: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 'version-1',
        sourceId: 'https://example.test/books',
        sourceType: 'book',
        status: 'candidate',
        payload: {
          canonical_url: 'https://example.test/books',
          keyword: 'sample',
          submitted_by: 'tenant-console',
          autonomous_build: {
            decision: 'canary',
            strategy: 'deterministic_patch',
            trigger: 'configured_catalog',
            agent_run_id: 'run-autonomous-1',
            probe: {
              search_status: 'ok',
              toc_status: 'ok',
              content_status: 'failed',
              failure_reason: 'content endpoint returned html',
            },
            validation: {
              grade: 'B',
              quality_score: 80,
            },
          },
        },
        createdBy: 'tenant-console',
        createdAt: '2026-07-12T10:00:00Z',
        latestRun: {
          id: 'run-1',
          trigger: 'manual',
          score: 88,
          grade: 'B',
          createdAt: '2026-07-12T10:05:00Z',
        },
      },
    ],
    meta: { total: 1 },
    trace_id: null,
  }),
}))

vi.mock('@/api/modules/operations', async () => {
  const actual = await vi.importActual<typeof import('@/api/modules/operations')>('@/api/modules/operations')
  return {
    ...actual,
    listSourceBuildCandidates: operationsMocks.listSourceBuildCandidates,
  }
})

import { SourceBuildsPage } from './SourceBuildsPage'

test('source builds page renders candidate url, keyword, latest grade, and automation summary', async () => {
  render(<SourceBuildsPage />)

  expect(await screen.findByRole('heading', { name: 'Source build candidates' })).toBeInTheDocument()
  expect(screen.getByText('https://example.test/books')).toBeInTheDocument()
  expect(screen.getByText('sample')).toBeInTheDocument()
  expect(screen.getByText('candidate')).toBeInTheDocument()
  expect(screen.getByText('B')).toBeInTheDocument()
  expect(screen.getByText('canary')).toBeInTheDocument()
  expect(screen.getByText('configured_catalog 路 deterministic_patch')).toBeInTheDocument()
  expect(screen.getByText('validation: B (80)')).toBeInTheDocument()
  expect(screen.getByText('search/toc/content: ok / ok / failed')).toBeInTheDocument()
  expect(screen.getByText('content endpoint returned html')).toBeInTheDocument()
})
