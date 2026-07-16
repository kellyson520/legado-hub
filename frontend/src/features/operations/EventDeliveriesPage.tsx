import { useEffect, useMemo, useState } from 'react'

import {
  listEventDeliveries,
  listEventDeliveryAttempts,
  subscribeOperationEvents,
  type OperationDeliveryAttemptRow,
  type OperationDeliveryRow,
  type OperationStreamEvent,
} from '@/api/modules/operations'
import { PaginationToolbar } from '@/components/data/PaginationToolbar'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Card } from '@/components/ui/card'
import { useServerPagination } from '@/hooks/useServerPagination'

const STREAM_RETRY_DELAY_MS = 2_000

function getDeliveryId(delivery: Partial<OperationDeliveryRow>) {
  return delivery.eventId ?? delivery.event_id ?? ''
}

function getDeliveryEventType(delivery: Partial<OperationDeliveryRow>) {
  return delivery.eventType ?? delivery.event_type ?? 'event.delivery'
}

function getDeliveryTenant(delivery: Partial<OperationDeliveryRow>) {
  return delivery.tenantId ?? delivery.tenant_id ?? '-'
}

function getDeliveryAttemptCount(delivery: Partial<OperationDeliveryRow>) {
  return delivery.attemptCount ?? delivery.attempt_count ?? 0
}

function getAttemptNumber(attempt: OperationDeliveryAttemptRow) {
  return attempt.attemptNo ?? attempt.attempt_no ?? 0
}

function getAttemptStatusCode(attempt: OperationDeliveryAttemptRow) {
  return attempt.statusCode ?? attempt.status_code ?? null
}

function getAttemptError(attempt: OperationDeliveryAttemptRow) {
  return attempt.errorMessage ?? attempt.error_message ?? null
}

function mergeDeliveryRow(current: OperationDeliveryRow[], event: OperationStreamEvent) {
  if (event.event !== 'event.delivery') return current
  const payload = event.data as Record<string, unknown>
  const eventId = String(payload.event_id ?? payload.eventId ?? '')
  if (!eventId) return current

  const nextRow: OperationDeliveryRow = {
    eventId,
    eventType: typeof (payload.event_type ?? payload.eventType) === 'string' ? String(payload.event_type ?? payload.eventType) : undefined,
    tenantId: typeof (payload.tenant_id ?? payload.tenantId) === 'string' ? String(payload.tenant_id ?? payload.tenantId) : undefined,
    targetUrl: typeof (payload.target_url ?? payload.targetUrl) === 'string' ? String(payload.target_url ?? payload.targetUrl) : undefined,
    dedupeKey: typeof (payload.dedupe_key ?? payload.dedupeKey) === 'string' ? String(payload.dedupe_key ?? payload.dedupeKey) : null,
    status: String(payload.status ?? 'pending'),
    attemptCount: Number(payload.attempt_count ?? payload.attemptCount ?? 0),
    lastError: typeof (payload.last_error ?? payload.lastError) === 'string' ? String(payload.last_error ?? payload.lastError) : null,
    nextAttemptAt: typeof (payload.next_attempt_at ?? payload.nextAttemptAt) === 'string' ? String(payload.next_attempt_at ?? payload.nextAttemptAt) : null,
    deliveredAt: typeof (payload.delivered_at ?? payload.deliveredAt) === 'string' ? String(payload.delivered_at ?? payload.deliveredAt) : null,
    createdAt: typeof (payload.created_at ?? payload.createdAt) === 'string' ? String(payload.created_at ?? payload.createdAt) : null,
  }

  const index = current.findIndex((item) => getDeliveryId(item) === eventId)
  if (index === -1) return [nextRow, ...current]

  const merged = [...current]
  merged[index] = { ...merged[index], ...nextRow }
  return merged
}

export function EventDeliveriesPage() {
  const pagination = useServerPagination<OperationDeliveryRow>({
    pageSize: 20,
    load: ({ page, pageSize, search }) => listEventDeliveries({ page, page_size: pageSize, search }),
  })
  const { rows, meta, loading, error: loadError } = pagination
  const [streamRows, setStreamRows] = useState<OperationDeliveryRow[]>([])
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [attempts, setAttempts] = useState<OperationDeliveryAttemptRow[]>([])
  const [streamState, setStreamState] = useState<'connecting' | 'live' | 'offline'>('connecting')

  useEffect(() => {
    let mounted = true
    let unsubscribe = () => {}
    let retryTimer: number | null = null

    function scheduleReconnect() {
      if (!mounted || retryTimer !== null) return
      retryTimer = window.setTimeout(() => {
        retryTimer = null
        void connect()
      }, STREAM_RETRY_DELAY_MS)
    }

    async function connect() {
      if (!mounted) return
      setStreamState('connecting')
      try {
        unsubscribe = await subscribeOperationEvents({
          onEvent: (event) => {
            if (!mounted) return
            setStreamState('live')
            setStreamRows((current) => mergeDeliveryRow(current, event))
          },
          onDisconnect: () => {
            if (!mounted) return
            setStreamState('offline')
            scheduleReconnect()
          },
        })
        if (mounted) setStreamState('live')
      } catch {
        if (mounted) {
          setStreamState('offline')
          scheduleReconnect()
        }
      }
    }

    void connect()

    return () => {
      mounted = false
      if (retryTimer !== null) {
        window.clearTimeout(retryTimer)
      }
      unsubscribe()
    }
  }, [])

  const deliveries = useMemo(() => {
    return streamRows.reduce((current, event) => {
      const streamEvent: OperationStreamEvent = {
        event: 'event.delivery',
        data: event as unknown as Record<string, unknown>,
      }
      return mergeDeliveryRow(current, streamEvent)
    }, rows)
  }, [rows, streamRows])

  useEffect(() => {
    setSelectedEventId((current) => current ?? getDeliveryId(deliveries[0] ?? {}))
  }, [deliveries])

  useEffect(() => {
    let mounted = true
    if (!selectedEventId) {
      setAttempts([])
      return
    }
    const eventId = selectedEventId

    async function loadAttempts() {
      const response = await listEventDeliveryAttempts(eventId)
      if (!mounted) return
      setAttempts(response.data)
    }

    void loadAttempts()
    return () => {
      mounted = false
    }
  }, [selectedEventId])

  const selectedDelivery = useMemo(
    () => deliveries.find((delivery) => getDeliveryId(delivery) === selectedEventId) ?? null,
    [deliveries, selectedEventId]
  )

  return (
    <ConsoleLayout
      eyebrow="Operations"
      title="Event deliveries"
      description="查看 webhook 投递状态、失败历史与最近流式事件，辅助排查 event delivery 的 retry、dedupe 和实时推送链路。"
      actions={
        <span className="rounded-full border border-border bg-muted/50 px-3 py-1 text-xs text-muted-foreground">
          {streamState === 'live' ? 'Live updates connected' : streamState === 'connecting' ? 'Connecting stream…' : 'Stream offline'}
        </span>
      }
    >
      <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <PaginationToolbar
            page={meta.page}
            totalPages={meta.total_pages}
            total={meta.total}
            searchInput={pagination.searchInput}
            appliedSearch={pagination.appliedSearch}
            loading={loading}
            searchLabel="搜索事件投递"
            onSearchInput={pagination.setSearchInput}
            onSearch={() => pagination.submitSearch()}
            onClearSearch={pagination.clearSearch}
            onPageChange={pagination.goToPage}
          />
          {loadError ? (
            <Card className="m-4 flex flex-wrap items-center gap-3 p-4 text-sm text-destructive" role="alert">
              <span>Failed to load event deliveries.</span>
              <button type="button" className="underline" onClick={() => pagination.retry()}>重试</button>
            </Card>
          ) : null}
          <table className="min-w-full divide-y divide-border text-sm">
            <thead className="bg-muted/40 text-left text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Event</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Tenant</th>
                <th className="px-4 py-3 font-medium">Attempts</th>
                <th className="px-4 py-3 font-medium">Last error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {deliveries.map((delivery) => {
                const eventId = getDeliveryId(delivery)
                const isSelected = eventId === selectedEventId
                return (
                  <tr key={eventId} className={isSelected ? 'bg-muted/30' : undefined}>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        className="text-left font-medium text-foreground hover:text-primary"
                        onClick={() => setSelectedEventId(eventId)}
                        aria-label={`${getDeliveryEventType(delivery)} ${eventId}`}
                      >
                        <span className="block">{getDeliveryEventType(delivery)}</span>
                        <span className="block text-xs text-muted-foreground">{eventId}</span>
                      </button>
                    </td>
                    <td className="px-4 py-3">{delivery.status}</td>
                    <td className="px-4 py-3">{getDeliveryTenant(delivery)}</td>
                    <td className="px-4 py-3">{getDeliveryAttemptCount(delivery)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{delivery.lastError ?? delivery.last_error ?? '-'}</td>
                  </tr>
                )
              })}
              {!loading && deliveries.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-muted-foreground" colSpan={5}>
                    No event deliveries yet
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <aside className="rounded-2xl border border-border bg-card p-4">
          <div className="space-y-1 border-b border-border pb-4">
            <h2 className="text-sm font-semibold text-foreground">Attempt history</h2>
            <p className="text-xs text-muted-foreground">
              {selectedDelivery ? `Inspecting ${getDeliveryEventType(selectedDelivery)}` : 'Select a delivery row to inspect retry history.'}
            </p>
          </div>
          <div className="mt-4 space-y-3">
            {attempts.map((attempt) => (
              <div key={attempt.id} className="rounded-xl border border-border bg-muted/20 p-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium text-foreground">Attempt {getAttemptNumber(attempt)}</span>
                  <span className="text-xs text-muted-foreground">
                    {attempt.delivered ? 'delivered' : `HTTP ${getAttemptStatusCode(attempt) ?? '-'}`}
                  </span>
                </div>
                <p className="mt-2 text-muted-foreground">{getAttemptError(attempt) ?? 'No error payload'}</p>
              </div>
            ))}
            {attempts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No persisted attempts for the selected delivery.</p>
            ) : null}
          </div>
        </aside>
      </div>
    </ConsoleLayout>
  )
}
