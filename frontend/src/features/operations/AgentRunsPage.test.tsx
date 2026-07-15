import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

const operationsMocks = vi.hoisted(() => ({
  listOperationAgentRuns: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 'run-1',
        tenantId: 'api-key:7',
        agentKind: 'source_build',
        inputPayload: { url: 'https://example.test/books' },
        status: 'candidate',
        createdAt: '2026-07-12T13:00:00Z',
        toolInvocationCount: 2,
        acceptedCount: 1,
        rejectedCount: 1,
        evidenceCount: 3,
        latestToolName: 'rule.validate',
      },
    ],
    meta: { total: 1 },
    trace_id: null,
  }),
  getOperationAgentRun: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      id: 'run-1',
      tenantId: 'api-key:7',
      agentKind: 'source_build',
      inputPayload: { url: 'https://example.test/books' },
      status: 'candidate',
      createdAt: '2026-07-12T13:00:00Z',
      toolInvocationCount: 2,
      acceptedCount: 1,
      rejectedCount: 1,
      evidenceCount: 3,
      latestToolName: 'rule.validate',
      toolHistory: [
        {
          id: 'invoke-1',
          toolName: 'source.inspect',
          category: 'operate',
          arguments: { url: 'https://example.test/books' },
          createdAt: '2026-07-12T13:01:00Z',
          result: {
            id: 'result-1',
            status: 'accepted',
            data: { status: 'ok' },
            errorCode: null,
            createdAt: '2026-07-12T13:01:05Z',
          },
          evidence: [
            {
              id: 'evidence-1',
              evidenceType: 'dom_snapshot',
              resourceId: 'snapshot-1',
              payload: { selector: '#book-list' },
              createdAt: '2026-07-12T13:01:06Z',
            },
          ],
        },
      ],
    },
    meta: {},
    trace_id: null,
  }),
}))

vi.mock('@/api/modules/operations', async () => {
  const actual = await vi.importActual<typeof import('@/api/modules/operations')>('@/api/modules/operations')
  return {
    ...actual,
    listOperationAgentRuns: operationsMocks.listOperationAgentRuns,
    getOperationAgentRun: operationsMocks.getOperationAgentRun,
  }
})

import { AgentRunsPage } from './AgentRunsPage'

beforeEach(() => {
  operationsMocks.listOperationAgentRuns.mockClear()
  operationsMocks.getOperationAgentRun.mockClear()
})

test('agent runs page renders recent run summaries', async () => {
  render(<AgentRunsPage />)

  expect(await screen.findByRole('heading', { name: 'Agent runs' })).toBeInTheDocument()
  expect(await screen.findByText('source_build')).toBeInTheDocument()
  expect(screen.getByText('api-key:7')).toBeInTheDocument()
  expect(screen.getByText('Tools 2 · Accepted 1 · Rejected 1')).toBeInTheDocument()
  expect(screen.getByText('Evidence 3 · Latest rule.validate')).toBeInTheDocument()
})

test('agent runs page loads run detail on inspect', async () => {
  render(<AgentRunsPage />)

  const button = await screen.findByRole('button', { name: 'Inspect source_build run-1' })
  fireEvent.click(button)

  await waitFor(() => {
    expect(operationsMocks.getOperationAgentRun).toHaveBeenCalledWith('run-1')
  })
  expect(await screen.findByText('source.inspect')).toBeInTheDocument()
  expect(screen.getByText('Result accepted · Evidence 1')).toBeInTheDocument()
  expect(screen.getByText('dom_snapshot · snapshot-1')).toBeInTheDocument()
})
