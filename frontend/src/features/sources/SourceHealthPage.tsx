import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Eye } from 'lucide-react'

import { useLanguage } from '@/app/providers/LanguageProvider'
import {
  listSourceHealth,
  probeSourceHealth,
  probeSourceHealthBatch,
  recoverSourceHealth,
  type SourceHealthRow,
} from '@/api/modules/sourceHealth'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { StatusBadge } from '@/components/data/StatusBadge'
import { StatusMessage } from '@/components/data/StatusMessage'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useServerPagination } from '@/hooks/useServerPagination'

const PAGE_SIZE = 20
const PROBE_KEYWORDS = ['捞尸人', '斗罗大陆', '剑来']

function tone(status: string) {
  if (status === 'healthy' || status === 'ok') return 'text-emerald-600 dark:text-emerald-400'
  if (status === 'degraded') return 'text-amber-600 dark:text-amber-400'
  if (status === 'blocked' || status === 'failed' || status === 'dead') return 'text-rose-600 dark:text-rose-400'
  if (status === 'disabled') return 'text-slate-500 dark:text-slate-400'
  return 'text-muted-foreground'
}

type HealthStatus = 'healthy' | 'degraded' | 'blocked' | 'dead' | 'unprobed' | 'unknown' | 'disabled'

interface HealthSummary {
  total: number
  healthy: number
  degraded: number
  blocked: number
  dead: number
  unprobed: number
  unknown: number
  disabled: number
}

const HEALTH_STATUSES: HealthStatus[] = ['healthy', 'degraded', 'blocked', 'dead', 'unprobed', 'unknown', 'disabled']

function displayHealthStatus(row: Pick<SourceHealthRow, 'health_status' | 'failure_reason'>): HealthStatus {
  if (row.health_status === 'unknown' && row.failure_reason === 'not_probed') return 'unprobed'
  return HEALTH_STATUSES.includes(row.health_status as HealthStatus)
    ? row.health_status as HealthStatus
    : 'unknown'
}

function countPageStatuses(rows: SourceHealthRow[]): HealthSummary {
  const summary: HealthSummary = {
    total: rows.length,
    healthy: 0,
    degraded: 0,
    blocked: 0,
    dead: 0,
    unprobed: 0,
    unknown: 0,
    disabled: 0,
  }
  rows.forEach((row) => {
    summary[displayHealthStatus(row)] += 1
  })
  return summary
}

function readCount(counts: Record<string, number> | undefined, key: keyof HealthSummary, fallback: number) {
  const value = counts?.[key]
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : fallback
}

function MetricCard({ label, value, status }: { label: string; value: number | string; status?: HealthStatus }) {
  const accent = status === 'healthy'
    ? 'border-l-emerald-500'
    : status === 'degraded' || status === 'unprobed'
      ? 'border-l-amber-500'
      : status === 'blocked' || status === 'dead'
        ? 'border-l-rose-500'
        : status === 'disabled'
          ? 'border-l-slate-400'
        : status === 'unknown'
          ? 'border-l-slate-400'
          : 'border-l-primary'
  return (
    <Card className={`border-l-4 p-4 ${accent}`}>
      <p className="text-sm font-medium text-muted-foreground">{label}{value}</p>
    </Card>
  )
}

function HealthMetrics({ title, description, summary, prefix, unavailable }: {
  title: string
  description: string
  summary: HealthSummary
  prefix: '总' | '本页'
  unavailable?: boolean
}) {
  const { t } = useLanguage()
  const metrics: Array<{ key: keyof HealthSummary; label: string; status?: HealthStatus }> = [
    { key: 'total', label: `${prefix}计： ` },
    { key: 'healthy', label: `${prefix}健康： `, status: 'healthy' },
    { key: 'degraded', label: `${prefix}降级： `, status: 'degraded' },
    { key: 'blocked', label: `${prefix}阻断： `, status: 'blocked' },
    { key: 'dead', label: `${prefix}失效： `, status: 'dead' },
    { key: 'unprobed', label: `${prefix}未探测： `, status: 'unprobed' },
    { key: 'unknown', label: `${prefix}未知： `, status: 'unknown' },
    { key: 'disabled', label: `${prefix}禁用： `, status: 'disabled' },
  ]
  return (
    <section aria-labelledby={`${prefix}-health-summary`} className="space-y-3">
      <div>
        <h2 id={`${prefix}-health-summary`} className="text-base font-semibold text-foreground">{t(title)}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t(description)}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4 xl:grid-cols-7">
        {metrics.map((metric) => (
          <MetricCard
            key={metric.key}
            label={t(metric.label)}
            value={metric.key !== 'total' && unavailable ? '—' : summary[metric.key]}
            status={metric.status}
          />
        ))}
      </div>
    </section>
  )
}

export function SourceHealthPage() {
  const pagination = useServerPagination<SourceHealthRow>({
    pageSize: PAGE_SIZE,
    load: listSourceHealth,
  })
  const { rows, meta } = pagination
  const [actionError, setActionError] = useState<string | null>(null)
  const [batchPending, setBatchPending] = useState(false)
  const [pendingSourceIds, setPendingSourceIds] = useState<Set<number>>(() => new Set())
  const mountedRef = useRef(true)
  const nextActionRequestIdRef = useRef(0)
  const actionRequestIdsRef = useRef(new Map<number, number>())
  const pendingSourceIdsRef = useRef(new Set<number>())

  function setSourcePending(sourceId: number, pending: boolean) {
    if (!mountedRef.current) return
    if (pending) pendingSourceIdsRef.current.add(sourceId)
    else pendingSourceIdsRef.current.delete(sourceId)
    setPendingSourceIds((current) => {
      const next = new Set(current)
      if (pending) next.add(sourceId)
      else next.delete(sourceId)
      return next
    })
  }

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      nextActionRequestIdRef.current += 1
      actionRequestIdsRef.current.clear()
      pendingSourceIdsRef.current.clear()
    }
  }, [])

  async function handleSourceAction(
    sourceId: number,
    sourceName: string,
    verb: 'probe' | 'recover',
    action: (id: number) => Promise<unknown>
  ) {
    if (!mountedRef.current || pendingSourceIdsRef.current.has(sourceId)) return
    const actionRequestId = nextActionRequestIdRef.current + 1
    nextActionRequestIdRef.current = actionRequestId
    actionRequestIdsRef.current.set(sourceId, actionRequestId)
    setActionError(null)
    setSourcePending(sourceId, true)
    try {
      await action(sourceId)
      if (mountedRef.current && actionRequestIdsRef.current.get(sourceId) === actionRequestId) {
        pagination.reload()
      }
    } catch {
      if (mountedRef.current && actionRequestIdsRef.current.get(sourceId) === actionRequestId) {
        setActionError(`Unable to ${verb} ${sourceName}. Please try again.`)
      }
    } finally {
      if (mountedRef.current && actionRequestIdsRef.current.get(sourceId) === actionRequestId) {
        actionRequestIdsRef.current.delete(sourceId)
        setSourcePending(sourceId, false)
      }
    }
  }

  async function handleProbe(sourceId: number, sourceName: string) {
    await handleSourceAction(sourceId, sourceName, 'probe', probeSourceHealth)
  }

  async function handleRecover(sourceId: number, sourceName: string) {
    await handleSourceAction(sourceId, sourceName, 'recover', recoverSourceHealth)
  }

  async function handleBatchProbe() {
    if (!mountedRef.current || batchPending || !rows.length) return
    setBatchPending(true)
    setActionError(null)
    try {
      await probeSourceHealthBatch(rows.map((row) => row.source_id), PROBE_KEYWORDS)
      if (mountedRef.current) pagination.reload()
    } catch {
      if (mountedRef.current) setActionError('Unable to probe the visible source page. Please try again.')
    } finally {
      if (mountedRef.current) setBatchPending(false)
    }
  }

  const pageSummary = countPageStatuses(rows)
  const hasTotalStatusCounts = Boolean(
    meta.status_counts && Object.keys(meta.status_counts).some((key) => key !== 'total'),
  )
  const totalSummary: HealthSummary = {
    total: readCount(meta.status_counts, 'total', meta.total),
    healthy: hasTotalStatusCounts ? readCount(meta.status_counts, 'healthy', 0) : 0,
    degraded: hasTotalStatusCounts ? readCount(meta.status_counts, 'degraded', 0) : 0,
    blocked: hasTotalStatusCounts ? readCount(meta.status_counts, 'blocked', 0) : 0,
    dead: hasTotalStatusCounts ? readCount(meta.status_counts, 'dead', 0) : 0,
    unprobed: hasTotalStatusCounts ? readCount(meta.status_counts, 'unprobed', 0) : 0,
    unknown: hasTotalStatusCounts ? readCount(meta.status_counts, 'unknown', 0) : 0,
    disabled: hasTotalStatusCounts ? readCount(meta.status_counts, 'disabled', 0) : 0,
  }

  return (
    <ConsolePageShell
      eyebrow="Source Health"
      title="Source health control plane"
      description="展示 search / toc / content 三层状态、失败原因、分流策略，并提供重探测与恢复入口。"
    >
      <div className="space-y-6">
        <HealthMetrics
          title={hasTotalStatusCounts ? '全量健康统计' : '全量健康统计（状态分布不可用）'}
          description={hasTotalStatusCounts ? '按当前搜索条件汇总所有书源的健康状态。' : '当前后端未返回全量状态分布，已隐藏分项，仅显示总量。'}
          summary={totalSummary}
          prefix="总"
          unavailable={!hasTotalStatusCounts}
        />
        <HealthMetrics
          title="当前分页统计"
          description="只统计当前页面已加载的书源。"
          summary={pageSummary}
          prefix="本页"
        />
      </div>

      <Card className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-foreground">Book source health</h3>
          <div className="flex gap-3">
            <Button variant="outline" size="sm" onClick={() => void handleBatchProbe()} disabled={pagination.loading || batchPending || !rows.length}>智能探测本页</Button>
            <Link to="/sources" className="text-sm font-medium text-primary">
              Back to inventory
            </Link>
          </div>
        </div>

        <PaginatedListControls
          pagination={pagination}
          empty={!pagination.loading && rows.length === 0}
          loadingLabel="Loading"
          errorLabel="Unable to load source health. Please try again."
          emptyLabel="暂无书源健康记录。"
          searchLabel="搜索书源"
        />

        <StatusMessage tone="error" message={actionError} as="div" className="mb-4 text-rose-600" />

        <div className="space-y-4">
            {rows.map((row) => (
              <article key={row.source_id} className="rounded-md border border-border p-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h4 className="text-base font-semibold text-foreground">{row.source_name}</h4>
                    <p className="text-sm text-muted-foreground">{row.source_url}</p>
                    <div className={`mt-2 flex items-center gap-2 text-sm ${tone(displayHealthStatus(row))}`}>
                      <span>health: </span>
                      <StatusBadge status={displayHealthStatus(row)} />
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      reason:{' '}
                      <span>{row.failure_reason || '-'}</span>
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Link
                      to={`/sources/health/${row.source_id}`}
                      title="View source details"
                      aria-label="View source details"
                      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-input text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                    >
                      <Eye className="h-4 w-4" aria-hidden="true" />
                    </Link>
                    <Button
                      variant="outline"
                      size="sm"
                      aria-label={`Probe source ${row.source_name}`}
                      disabled={pendingSourceIds.has(row.source_id)}
                      onClick={() => void handleProbe(row.source_id, row.source_name)}
                    >
                      Probe source
                    </Button>
                    <Button
                      size="sm"
                      aria-label={`Recover source ${row.source_name}`}
                      disabled={pendingSourceIds.has(row.source_id)}
                      onClick={() => void handleRecover(row.source_id, row.source_name)}
                    >
                      Recover
                    </Button>
                  </div>
                </div>
                <div className="mt-4 grid gap-2 md:grid-cols-3">
                  <div className={`flex items-center justify-between rounded-md border border-border bg-muted/30 p-3 text-sm ${tone(row.search_status)}`}>
                    <span>search: </span>
                    <StatusBadge status={row.search_status} />
                  </div>
                  <div className={`flex items-center justify-between rounded-md border border-border bg-muted/30 p-3 text-sm ${tone(row.toc_status)}`}>
                    <span>toc: </span>
                    <StatusBadge status={row.toc_status} />
                  </div>
                  <div className={`flex items-center justify-between rounded-md border border-border bg-muted/30 p-3 text-sm ${tone(row.content_status)}`}>
                    <span>content: </span>
                    <StatusBadge status={row.content_status} />
                  </div>
                </div>
              </article>
            ))}
        </div>
      </Card>
    </ConsolePageShell>
  )
}
