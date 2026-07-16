import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Eye } from 'lucide-react'

import {
  listSourceHealth,
  probeSourceHealth,
  recoverSourceHealth,
  type SourceHealthRow,
} from '@/api/modules/sourceHealth'
import { ListStatus } from '@/components/data/ListStatus'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { PaginationToolbar } from '@/components/data/PaginationToolbar'
import { useServerPagination } from '@/hooks/useServerPagination'

const PAGE_SIZE = 20

function tone(status: string) {
  if (status === 'healthy' || status === 'ok') return 'text-emerald-600 dark:text-emerald-400'
  if (status === 'degraded') return 'text-amber-600 dark:text-amber-400'
  if (status === 'blocked' || status === 'failed' || status === 'dead') return 'text-rose-600 dark:text-rose-400'
  return 'text-muted-foreground'
}

export function SourceHealthPage() {
  const pagination = useServerPagination<SourceHealthRow>({
    pageSize: PAGE_SIZE,
    load: ({ page, pageSize, search }) => listSourceHealth({ page, page_size: pageSize, search }),
  })
  const { rows, meta, loading, error: loadError } = pagination
  const [actionError, setActionError] = useState<string | null>(null)
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

  const summary = rows.reduce(
    (acc, row) => {
      acc[row.health_status] = (acc[row.health_status] || 0) + 1
      return acc
    },
    {} as Record<string, number>
  )

  return (
    <ConsoleLayout
      eyebrow="Source Health"
      title="Source health control plane"
      description="展示 search / toc / content 三层状态、失败原因、分流策略，并提供重探测与恢复入口。"
    >
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="p-4">Total: {meta.total}</Card>
        <Card className="p-4">本页 Healthy: {summary.healthy || 0}</Card>
        <Card className="p-4">本页 Blocked: {summary.blocked || 0}</Card>
        <Card className="p-4">本页 Dead: {summary.dead || 0}</Card>
      </div>

      <Card className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-foreground">Book source health</h3>
          <div className="flex gap-3">
            <Button variant="outline" size="sm" onClick={() => pagination.reload()} disabled={loading}>Probe now</Button>
            <Link to="/sources" className="text-sm font-medium text-primary">
              Back to inventory
            </Link>
          </div>
        </div>

        <ListStatus
          loading={loading}
          error={loadError}
          empty={!loading && rows.length === 0}
          onRetry={pagination.retry}
          loadingLabel="Loading"
          errorLabel="Unable to load source health. Please try again."
          emptyLabel="暂无书源健康记录。"
        />

        {actionError ? <div role="alert" className="mb-4 text-sm text-rose-600">{actionError}</div> : null}

        <PaginationToolbar
          page={meta.page}
          totalPages={meta.total_pages}
          total={meta.total}
          searchInput={pagination.searchInput}
          appliedSearch={pagination.appliedSearch}
          loading={loading}
          searchLabel="搜索书源"
          onSearchInput={pagination.setSearchInput}
          onSearch={() => pagination.submitSearch()}
          onClearSearch={pagination.clearSearch}
          onPageChange={pagination.goToPage}
        />

        <div className="space-y-4">
            {rows.map((row) => (
              <article key={row.source_id} className="rounded-md border border-border p-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h4 className="text-base font-semibold text-foreground">{row.source_name}</h4>
                    <p className="text-sm text-muted-foreground">{row.source_url}</p>
                    <p className={`mt-2 text-sm ${tone(row.health_status)}`}>health: {row.health_status}</p>
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
                  <div className={`rounded-md border border-border bg-muted/30 p-3 text-sm ${tone(row.search_status)}`}>
                    search: {row.search_status}
                  </div>
                  <div className={`rounded-md border border-border bg-muted/30 p-3 text-sm ${tone(row.toc_status)}`}>
                    toc: {row.toc_status}
                  </div>
                  <div className={`rounded-md border border-border bg-muted/30 p-3 text-sm ${tone(row.content_status)}`}>
                    content: {row.content_status}
                  </div>
                </div>
              </article>
            ))}
        </div>
      </Card>
    </ConsoleLayout>
  )
}
