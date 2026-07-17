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
          source_audit: {
            status: 'passed',
            attempt: 1,
            max_attempts: 5,
            score: 100,
            grade: 'A',
            test_run_pending: false,
            report: {
              status: 'passed',
              total_elapsed_ms: 480,
              stages: {
                search: { status: 'ok', elapsed_ms: 120 },
                toc: { status: 'ok', elapsed_ms: 160 },
                content: { status: 'ok', elapsed_ms: 200 },
              },
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

test('source builds page renders candidate url, audit trace, latest grade, and automation summary', async () => {
  render(<SourceBuildsPage />)

  expect(await screen.findByRole('heading', { name: '书源构建候选' })).toBeInTheDocument()
  expect(screen.getByText('https://example.test/books')).toBeInTheDocument()
  expect(screen.getByText('sample')).toBeInTheDocument()
  expect(screen.getByText('候选')).toBeInTheDocument()
  expect(screen.getByText('B')).toBeInTheDocument()
  expect(screen.getByText('审计： 通过 · 1/5 · A')).toBeInTheDocument()
  expect(screen.getByText('搜索/目录/正文： 正常 / 正常 / 正常 · 480ms')).toBeInTheDocument()
  expect(screen.getByText('解析总耗时： 480ms')).toBeInTheDocument()
  expect(screen.getByText('canary')).toBeInTheDocument()
  expect(screen.getByText('configured_catalog 路 deterministic_patch')).toBeInTheDocument()
  expect(screen.getByText('验证： B (80)')).toBeInTheDocument()
  expect(screen.getByText('搜索/目录/正文： 正常 / 正常 / 已失败')).toBeInTheDocument()
  expect(screen.getByText('content endpoint returned html')).toBeInTheDocument()
})

test('source builds page announces terminal audit failure reason and timing', async () => {
  operationsMocks.listSourceBuildCandidates.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 'version-audit-failed',
        sourceId: 'https://example.test/audit-failed',
        sourceType: 'book',
        status: 'failed',
        payload: {
          canonical_url: 'https://example.test/audit-failed',
          source_audit: {
            status: 'failed',
            attempt: 5,
            max_attempts: 5,
            score: 0,
            grade: 'F',
            report: {
              status: 'failed',
              reason: 'content parse failed',
              total_elapsed_ms: 480,
              stages: {
                search: { status: 'ok', elapsed_ms: 120 },
                toc: { status: 'ok', elapsed_ms: 160 },
                content: { status: 'failed', elapsed_ms: 200 },
              },
            },
          },
        },
      },
    ],
    meta: { total: 1 },
    trace_id: null,
  })

  render(<SourceBuildsPage />)

  expect(await screen.findByText('审计： 已失败 · 5/5 · F')).toBeInTheDocument()
  expect(screen.getByText('搜索/目录/正文： 正常 / 正常 / 已失败 · 480ms')).toBeInTheDocument()
  expect(screen.getByText('解析总耗时： 480ms')).toBeInTheDocument()
  expect(screen.getByText('content parse failed')).toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('审计： 已失败 · 5/5 · F')
})
