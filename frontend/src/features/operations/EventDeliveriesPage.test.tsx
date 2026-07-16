import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

const operationsMocks = vi.hoisted(() => {
  const state: {
    streamHandler: ((event: {
      event: string
      data: {
        event_id: string
        event_type?: string
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

test('event deliveries page keeps unknown stream events outside the current server page', async () => {
  render(<EventDeliveriesPage />)

  expect(await screen.findByText('chapter.ready')).toBeInTheDocument()
  await waitFor(() => expect(operationsMocks.state.streamHandler).not.toBeNull())

  await act(async () => {
    operationsMocks.state.streamHandler?.({
      event: 'event.delivery',
      data: {
        event_id: 'evt-outside-page',
        event_type: 'chapter.updated',
        tenant_id: 'tenant-other',
        status: 'pending',
        attempt_count: 0,
      },
    })
  })

  expect(screen.queryByText('evt-outside-page')).not.toBeInTheDocument()
  expect(screen.getByText('chapter.ready')).toBeInTheDocument()
})

test('event deliveries page resets stream scope after pagination and search', async () => {
  operationsMocks.listEventDeliveries
    .mockResolvedValueOnce({
      success: true,
      code: 'OK',
      message: 'ok',
      data: [
        {
          eventId: 'evt-page-1',
          eventType: 'chapter.page.one',
          tenantId: 'tenant-page',
          status: 'pending',
          attemptCount: 0,
          lastError: null,
        },
      ],
      meta: { page: 1, page_size: 20, total: 2, total_pages: 2 },
      trace_id: null,
    })
    .mockResolvedValueOnce({
      success: true,
      code: 'OK',
      message: 'ok',
      data: [
        {
          eventId: 'evt-page-2',
          eventType: 'chapter.page.two',
          tenantId: 'tenant-page',
          status: 'pending',
          attemptCount: 0,
          lastError: null,
        },
      ],
      meta: { page: 2, page_size: 20, total: 2, total_pages: 2 },
      trace_id: null,
    })
    .mockResolvedValueOnce({
      success: true,
      code: 'OK',
      message: 'ok',
      data: [
        {
          eventId: 'evt-search',
          eventType: 'chapter.search.result',
          tenantId: 'tenant-search',
          status: 'pending',
          attemptCount: 0,
          lastError: null,
        },
      ],
      meta: { page: 1, page_size: 20, total: 1, total_pages: 1 },
      trace_id: null,
    })

  render(<EventDeliveriesPage />)

  expect(await screen.findByText('chapter.page.one')).toBeInTheDocument()
  await waitFor(() => expect(operationsMocks.state.streamHandler).not.toBeNull())

  fireEvent.click(screen.getByRole('button', { name: '下一页' }))
  expect(await screen.findByText('chapter.page.two')).toBeInTheDocument()
  expect(screen.queryByText('chapter.page.one')).not.toBeInTheDocument()

  fireEvent.change(screen.getByRole('textbox', { name: '搜索事件投递' }), { target: { value: 'search' } })
  fireEvent.click(screen.getByRole('button', { name: '搜索' }))
  expect(await screen.findByText('chapter.search.result')).toBeInTheDocument()
  expect(screen.queryByText('chapter.page.two')).not.toBeInTheDocument()

  await act(async () => {
    operationsMocks.state.streamHandler?.({
      event: 'event.delivery',
      data: {
        event_id: 'evt-page-1',
        event_type: 'chapter.stale',
        tenant_id: 'tenant-page',
        status: 'retrying',
        attempt_count: 1,
      },
    })
  })
  expect(screen.queryByText('chapter.stale')).not.toBeInTheDocument()
  expect(operationsMocks.listEventDeliveries).toHaveBeenLastCalledWith({ page: 1, page_size: 20, search: 'search' })
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
