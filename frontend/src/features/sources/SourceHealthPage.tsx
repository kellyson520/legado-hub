import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Eye } from 'lucide-react'

import {
  listSourceHealth,
  probeSourceHealth,
  recoverSourceHealth,
  type SourceHealthRow,
} from '@/api/modules/sourceHealth'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

function tone(status: string) {
  if (status === 'healthy' || status === 'ok') return 'text-emerald-600 dark:text-emerald-400'
  if (status === 'degraded') return 'text-amber-600 dark:text-amber-400'
  if (status === 'blocked' || status === 'failed' || status === 'dead') return 'text-rose-600 dark:text-rose-400'
  return 'text-muted-foreground'
}

export function SourceHealthPage() {
  const [rows, setRows] = useState<SourceHealthRow[]>([])
  const [loading, setLoading] = useState(true)

  async function load() {
    const response = await listSourceHealth({ page: 1, page_size: 20 })
    setRows(response.data)
    setLoading(false)
  }

  useEffect(() => {
    void load()
  }, [])

  async function handleProbe(sourceId: number) {
    await probeSourceHealth(sourceId)
    await load()
  }

  async function handleRecover(sourceId: number) {
    await recoverSourceHealth(sourceId)
    await load()
  }

  const summary = rows.reduce(
    (acc, row) => {
      acc.total += 1
      acc[row.health_status] = (acc[row.health_status] || 0) + 1
      return acc
    },
    { total: 0 } as Record<string, number>
  )

  return (
    <ConsoleLayout
      eyebrow="Source Health"
      title="Source health control plane"
      description="展示 search / toc / content 三层状态、失败原因、分流策略，并提供重探测与恢复入口。"
    >
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="p-4">Total: {summary.total || 0}</Card>
        <Card className="p-4">Healthy: {summary.healthy || 0}</Card>
        <Card className="p-4">Blocked: {summary.blocked || 0}</Card>
        <Card className="p-4">Dead: {summary.dead || 0}</Card>
      </div>

      <Card className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-foreground">Book source health</h3>
          <div className="flex gap-3">
            <Button variant="outline" size="sm" onClick={() => void load()}>Probe now</Button>
            <Link to="/sources" className="text-sm font-medium text-primary">
              Back to inventory
            </Link>
          </div>
        </div>

        {loading ? (
          <div className="text-sm text-muted-foreground">Loading</div>
        ) : (
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
                    <Button variant="outline" size="sm" onClick={() => void handleProbe(row.source_id)}>Probe source</Button>
                    <Button size="sm" onClick={() => void handleRecover(row.source_id)}>Recover</Button>
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
        )}
      </Card>
    </ConsoleLayout>
  )
}
