import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

const operationsMocks = vi.hoisted(() => {
  const state: {
    streamHandler: ((event: {
      event: string
      data: {
        event_id: string
        status: string
        attempt_count: number
        tenant_id: string
        last_error?: string | null
      }
    }) => void) | null
  } = { streamHandler: null }

  const subscribeOperationEvents = vi.fn().mockImplementation(async ({ onEvent }) => {
    state.streamHandler = onEvent
    return () => {
      state.streamHandler = null
    }
  })

  return {
    state,
    subscribeOperationEvents,
    listEventDeliveries: vi.fn().mockResolvedValue({
      success: true,
      code: 'OK',
      message: 'ok',
      data: [
        {
          eventId: 'evt-1',
          eventType: 'chapter.ready',
          tenantId: 'tenant-stream',
          targetUrl: 'https://callback.test/webhook',
          dedupeKey: 'chapter.ready:c1',
          status: 'pending',
          attemptCount: 0,
          lastError: null,
          createdAt: '2026-07-11T10:00:00Z',
        },
      ],
      meta: { total: 1 },
      trace_id: null,
    }),
    listEventDeliveryAttempts: vi.fn().mockResolvedValue({
      success: true,
      code: 'OK',
      message: 'ok',
      data: [],
      meta: { total: 0 },
      trace_id: null,
    }),
  }
})

vi.mock('@/api/modules/operations', () => ({
  listEventDeliveries: operationsMocks.listEventDeliveries,
  listEventDeliveryAttempts: operationsMocks.listEventDeliveryAttempts,
  subscribeOperationEvents: operationsMocks.subscribeOperationEvents,
}))

import { EventDeliveriesPage } from './EventDeliveriesPage'

beforeEach(() => {
  operationsMocks.state.streamHandler = null
  operationsMocks.subscribeOperationEvents.mockClear()
  operationsMocks.listEventDeliveries.mockClear()
  operationsMocks.listEventDeliveryAttempts.mockClear()
  vi.useRealTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

test('event deliveries page shows initial rows and applies stream updates', async () => {
  render(<EventDeliveriesPage />)

  expect(await screen.findByRole('heading', { name: 'Event deliveries' })).toBeInTheDocument()
  expect(await screen.findByText('chapter.ready')).toBeInTheDocument()
  expect(screen.getByText('pending')).toBeInTheDocument()

  await waitFor(() => expect(operationsMocks.state.streamHandler).not.toBeNull())
  await act(async () => {
    operationsMocks.state.streamHandler?.({
      event: 'event.delivery',
      data: {
        event_id: 'evt-1',
        tenant_id: 'tenant-stream',
        status: 'retrying',
        attempt_count: 1,
        last_error: 'upstream unavailable',
      },
    })
  })

  expect(await screen.findByText('retrying')).toBeInTheDocument()
  expect(screen.getByText('upstream unavailable')).toBeInTheDocument()
})

test('event deliveries page loads attempts for the selected delivery', async () => {
  operationsMocks.listEventDeliveryAttempts.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 1,
        eventId: 'evt-1',
        attemptNo: 1,
        delivered: false,
        statusCode: 503,
        errorMessage: 'upstream unavailable',
        createdAt: '2026-07-11T10:05:00Z',
      },
    ],
    meta: { total: 1 },
    trace_id: null,
  })

  render(<EventDeliveriesPage />)

  const rowButton = await screen.findByRole('button', { name: /chapter\.ready/i })
  fireEvent.click(rowButton)

  expect(await screen.findByText('Attempt history')).toBeInTheDocument()
  expect(screen.getByText('upstream unavailable')).toBeInTheDocument()
})

test('event deliveries page retries stream subscription after initial failure', async () => {
  vi.useFakeTimers()

  operationsMocks.listEventDeliveries.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [],
    meta: { total: 0 },
    trace_id: null,
  })
  operationsMocks.subscribeOperationEvents
    .mockRejectedValueOnce(new Error('stream unavailable'))
    .mockImplementationOnce(async ({ onEvent }) => {
      operationsMocks.state.streamHandler = onEvent
      return () => {
        operationsMocks.state.streamHandler = null
      }
    })

  render(<EventDeliveriesPage />)

  await act(async () => {
    await Promise.resolve()
  })
  expect(operationsMocks.subscribeOperationEvents).toHaveBeenCalledTimes(1)
  expect(screen.getByText('Stream offline')).toBeInTheDocument()

  await act(async () => {
    await vi.advanceTimersByTimeAsync(2_100)
    await Promise.resolve()
  })

  expect(operationsMocks.subscribeOperationEvents).toHaveBeenCalledTimes(2)

  vi.useRealTimers()
}, 10000)
