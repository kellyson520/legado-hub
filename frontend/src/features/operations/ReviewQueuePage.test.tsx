import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

const operationsMocks = vi.hoisted(() => ({
  listReviewQueueCandidates: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 'source-review-1',
        itemType: 'source_review',
        workId: 'source-version-ops-1',
        sourceChapterId: 'source-version-ops-1',
        proposalType: 'build_escalation',
        summary: 'Manual source build review required',
        subject: 'build_escalation',
        relation: 'review',
        objectName: 'https://example.test/escalated',
        evidence: 'risk:high, budget:blocked',
        status: 'candidate',
        createdBy: 'builder-1',
        createdAt: '2026-07-12T12:30:00Z',
      },
      {
        id: 'source-version-1',
        itemType: 'source_version',
        workId: 'sample',
        sourceChapterId: 'source-version-1',
        proposalType: 'source_version_publish',
        summary: 'Publish source candidate (grade A)',
        subject: 'book',
        relation: 'publish',
        objectName: 'https://example.test/books',
        evidence: 'https://example.test/books',
        status: 'candidate',
        payload: {
          source_audit: {
            status: 'passed',
            attempt: 1,
            max_attempts: 5,
            score: 100,
            grade: 'A',
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
        createdAt: '2026-07-12T12:00:00Z',
      },
      {
        id: 'source-audit-failed-1',
        itemType: 'source_review',
        workId: 'source-version-audit-failed',
        sourceChapterId: 'source-version-audit-failed',
        proposalType: 'source_audit_failed',
        summary: 'Source audit retry limit reached',
        subject: 'source_audit_failed',
        relation: 'review',
        objectName: 'https://example.test/audit-failed',
        evidence: 'content parse failed',
        status: 'candidate',
        payload: {
          audit_report: {
            status: 'failed',
            attempt: 5,
            max_attempts: 5,
            score: 0,
            grade: 'F',
            reason: 'content parse failed',
            total_elapsed_ms: 480,
            stages: {
              search: { status: 'ok', elapsed_ms: 120 },
              toc: { status: 'ok', elapsed_ms: 160 },
              content: { status: 'failed', elapsed_ms: 200 },
            },
          },
        },
        createdBy: 'system',
        createdAt: '2026-07-12T12:15:00Z',
      },
      {
        id: 'translation-1',
        itemType: 'translation_job',
        sourceChapterId: 'variant-1',
        proposalType: 'translation_review',
        summary: 'Translation memory review (2 chunks)',
        subject: 'zh -> en',
        relation: 'review',
        objectName: 'variant-1',
        evidence: 'Translated content preview',
        status: 'candidate',
        createdBy: 'translator-1',
        createdAt: '2026-07-12T11:00:00Z',
      },
      {
        id: 'proposal-1',
        itemType: 'knowledge_proposal',
        workId: 'w-review',
        sourceChapterId: 'c-review',
        proposalType: 'character_relation',
        summary: 'Lin trusts Mei',
        subject: 'Lin',
        relation: 'trusts',
        objectName: 'Mei',
        evidence: 'Lin trusts Mei',
        status: 'candidate',
        createdBy: 'agent',
        createdAt: '2026-07-12T10:00:00Z',
      },
    ],
    meta: { total: 5 },
    trace_id: null,
  }),
  resolveReviewQueueItem: vi.fn(),
}))

vi.mock('@/api/modules/operations', async () => {
  const actual = await vi.importActual<typeof import('@/api/modules/operations')>('@/api/modules/operations')
  return {
    ...actual,
    listReviewQueueCandidates: operationsMocks.listReviewQueueCandidates,
    resolveReviewQueueItem: operationsMocks.resolveReviewQueueItem,
  }
})

import { ReviewQueuePage } from './ReviewQueuePage'

beforeEach(() => {
  operationsMocks.resolveReviewQueueItem.mockReset()
})

test('review queue page renders source, knowledge, and translation review candidates', async () => {
  render(<MemoryRouter><ReviewQueuePage /></MemoryRouter>)

  expect(await screen.findByRole('heading', { name: '审核队列' })).toBeInTheDocument()
  expect(await screen.findByText('build_escalation')).toBeInTheDocument()
  expect(screen.getByText('Manual source build review required')).toBeInTheDocument()
  expect(screen.getByText('character_relation')).toBeInTheDocument()
  expect(screen.getAllByText('Lin trusts Mei')).toHaveLength(2)
  expect(screen.getByText('translation_review')).toBeInTheDocument()
  expect(screen.getByText('Translation memory review (2 chunks)')).toBeInTheDocument()
  expect(screen.getByText('source_version_publish')).toBeInTheDocument()
  expect(screen.getByText('Publish source candidate (grade A)')).toBeInTheDocument()
  expect(screen.getByText('审计： 通过 · 1/5 · A')).toBeInTheDocument()
  expect(screen.getByText('搜索/目录/正文： 正常 / 正常 / 正常 · 480ms')).toBeInTheDocument()
  expect(screen.getByText('source_audit_failed')).toBeInTheDocument()
  expect(screen.getByText('Source audit retry limit reached')).toBeInTheDocument()
  expect(screen.getByText('审计： 已失败 · 5/5 · F')).toBeInTheDocument()
  expect(screen.getByText('搜索/目录/正文： 正常 / 正常 / 已失败 · 480ms')).toBeInTheDocument()
  expect(screen.getAllByText('content parse failed')).toHaveLength(2)
  expect(screen.getByRole('alert')).toHaveTextContent('content parse failed')
  expect(screen.getByText('Translated content preview')).toBeInTheDocument()
})

test('review queue links source version candidates to rule audit', async () => {
  render(<MemoryRouter><ReviewQueuePage /></MemoryRouter>)

  expect(await screen.findByRole('link', { name: '审核规则' })).toHaveAttribute(
    'href',
    '/sources/rules/source-version-1'
  )
})

test('review queue page resolves source version publish candidates', async () => {
  operationsMocks.resolveReviewQueueItem.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      queueItemId: 'source-version-1',
      resultId: 'source-version-1',
      itemType: 'source_version',
      status: 'published',
      action: 'publish',
      reviewedBy: '1',
      publishedAt: '2026-07-12T12:30:00Z',
    },
    meta: {},
    trace_id: null,
  })

  render(<MemoryRouter><ReviewQueuePage /></MemoryRouter>)

  const button = await screen.findByRole('button', { name: '发布 source_version_publish' })
  fireEvent.click(button)

  await waitFor(() => {
    expect(operationsMocks.resolveReviewQueueItem).toHaveBeenCalledWith('source-version-1', {
      itemType: 'source_version',
      action: 'publish',
      memoryNote: undefined,
    })
  })
  await waitFor(() => {
    expect(screen.queryByText('Publish source candidate (grade A)')).not.toBeInTheDocument()
  })
  expect(screen.getByText('已为 source_version_publish 完成发布')).toBeInTheDocument()
})

test('review queue page resolves source review items', async () => {
  operationsMocks.resolveReviewQueueItem.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      queueItemId: 'source-review-1',
      resultId: 'source-review-1',
      itemType: 'source_review',
      status: 'resolved',
      action: 'resolve',
      reviewedBy: '1',
      resolvedAt: '2026-07-12T12:45:00Z',
      publishedAt: null,
    },
    meta: {},
    trace_id: null,
  })

  render(<MemoryRouter><ReviewQueuePage /></MemoryRouter>)

  const button = await screen.findByRole('button', { name: '解决 build_escalation' })
  fireEvent.click(button)

  await waitFor(() => {
    expect(operationsMocks.resolveReviewQueueItem).toHaveBeenCalledWith('source-review-1', {
      itemType: 'source_review',
      action: 'resolve',
      memoryNote: undefined,
    })
  })
  await waitFor(() => {
    expect(screen.queryByText('Manual source build review required')).not.toBeInTheDocument()
  })
  expect(screen.getByText('已为 build_escalation 完成解决')).toBeInTheDocument()
})

test('review queue page marks translation review items as reviewed', async () => {
  operationsMocks.resolveReviewQueueItem.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      queueItemId: 'translation-1',
      resultId: 'translation-1',
      itemType: 'translation_job',
      status: 'reviewed',
      action: 'review',
      reviewedBy: '1',
      publishedAt: null,
    },
    meta: {},
    trace_id: null,
  })

  render(<MemoryRouter><ReviewQueuePage /></MemoryRouter>)

  const button = await screen.findByRole('button', { name: '标记为已审核 translation_review' })
  fireEvent.click(button)

  await waitFor(() => {
    expect(operationsMocks.resolveReviewQueueItem).toHaveBeenCalledWith('translation-1', {
      itemType: 'translation_job',
      action: 'review',
      memoryNote: {
        source: 'operations.review_queue',
        proposal_type: 'translation_review',
      },
    })
  })
  await waitFor(() => {
    expect(screen.queryByText('Translation memory review (2 chunks)')).not.toBeInTheDocument()
  })
  expect(screen.getByText('已为 translation_review 完成标记为已审核')).toBeInTheDocument()
})
