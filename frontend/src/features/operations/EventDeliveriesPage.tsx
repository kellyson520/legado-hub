import { useEffect, useMemo, useState } from 'react'

import { useLanguage } from '@/app/providers/LanguageProvider'
import {
  listEventDeliveries,
  listEventDeliveryAttempts,
  subscribeOperationEvents,
  type OperationDeliveryAttemptRow,
  type OperationDeliveryRow,
  type OperationStreamEvent,
} from '@/api/modules/operations'
import { AttemptTimeline } from '@/components/detail/AttemptTimeline'
import { DataTable, type DataTableColumn } from '@/components/data/DataTable'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { StatusBadge } from '@/components/data/StatusBadge'
import { DetailPanel } from '@/components/detail/DetailPanel'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
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
  if (index === -1) return current

  const merged = [...current]
  merged[index] = { ...merged[index], ...nextRow }
  return merged
}

export function EventDeliveriesPage() {
  const { t } = useLanguage()
  const pagination = useServerPagination<OperationDeliveryRow>({
    pageSize: 20,
    load: listEventDeliveries,
  })
  const { rows } = pagination
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

  useEffect(() => {
    setStreamRows(rows)
  }, [rows])

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
    setSelectedEventId((current) => {
      if (current && deliveries.some((delivery) => getDeliveryId(delivery) === current)) {
        return current
      }
      return getDeliveryId(deliveries[0] ?? {}) || null
    })
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

  const deliveryColumns: DataTableColumn<OperationDeliveryRow>[] = [
    {
      id: 'event',
      header: t('Event'),
      cell: (delivery) => {
        const eventId = getDeliveryId(delivery)
        return (
          <button
            type="button"
            className="text-left font-medium text-foreground hover:text-primary"
            onClick={() => setSelectedEventId(eventId)}
            aria-label={`${getDeliveryEventType(delivery)} ${eventId}`}
          >
            <span className="block">{getDeliveryEventType(delivery)}</span>
            <span className="block text-xs text-muted-foreground">{eventId}</span>
          </button>
        )
      },
    },
    { id: 'status', header: t('Status'), cell: (delivery) => <StatusBadge status={delivery.status} /> },
    { id: 'tenant', header: t('Tenant'), cell: (delivery) => getDeliveryTenant(delivery) },
    { id: 'attempts', header: t('Attempts'), cell: (delivery) => getDeliveryAttemptCount(delivery) },
    {
      id: 'last-error',
      header: t('Last error'),
      cell: (delivery) => <span className="text-muted-foreground">{delivery.lastError ?? delivery.last_error ?? '-'}</span>,
    },
  ]

  const attemptItems = attempts.map((attempt) => ({
    id: attempt.id,
    label: t('Attempt {number}', { number: getAttemptNumber(attempt) }),
    status: attempt.delivered ? 'delivered' : 'failed',
    detail: attempt.delivered ? t('delivered') : (
      <>
        <span>{`${t('HTTP ')}${getAttemptStatusCode(attempt) ?? '-'}`}</span>
        {getAttemptError(attempt) ? <span className="mt-1 block">{getAttemptError(attempt)}</span> : <span className="mt-1 block">{t('No error payload')}</span>}
      </>
    ),
  }))

  return (
    <ConsolePageShell
      eyebrow="Operations"
      title="Event deliveries"
      description="查看 webhook 投递状态、失败历史与最近流式事件，辅助排查 event delivery 的 retry、dedupe 和实时推送链路。"
      actions={
        <span className="rounded-full border border-border bg-muted/50 px-3 py-1 text-xs text-muted-foreground">
          {t(streamState === 'live' ? 'Live updates connected' : streamState === 'connecting' ? 'Connecting stream…' : 'Stream offline')}
        </span>
      }
    >
      <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <div className="space-y-3">
          <PaginatedListControls
            pagination={pagination}
            empty={false}
            loadingLabel="正在加载事件投递…"
            errorLabel="Failed to load event deliveries."
            emptyLabel="No event deliveries yet"
            searchLabel="搜索事件投递"
          />
          <DataTable
            rows={deliveries}
            columns={deliveryColumns}
            getRowKey={getDeliveryId}
            getRowClassName={(delivery) => getDeliveryId(delivery) === selectedEventId ? 'bg-muted/30' : undefined}
            emptyLabel={t('No event deliveries yet')}
          />
        </div>

        <DetailPanel
          title={t('Attempt history')}
          description={selectedDelivery
            ? t('Inspecting {type}', { type: getDeliveryEventType(selectedDelivery) })
            : t('Select a delivery row to inspect retry history.')}
          emptyLabel={t('No persisted attempts for the selected delivery.')}
        >
          {attempts.length ? <AttemptTimeline items={attemptItems} /> : null}
        </DetailPanel>
      </div>
    </ConsolePageShell>
  )
}
