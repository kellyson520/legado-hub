import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  listSourceHealth,
  probeSourceHealth,
  recoverSourceHealth,
  type SourceHealthRow,
} from '@/api/modules/sourceHealth'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'

function tone(status: string) {
  if (status === 'healthy' || status === 'ok') return 'text-emerald-300'
  if (status === 'degraded') return 'text-amber-300'
  if (status === 'blocked' || status === 'failed' || status === 'dead') return 'text-rose-300'
  return 'text-zinc-400'
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
        <div className="rounded-[24px] border border-white/10 bg-black/20 p-5">Total: {summary.total || 0}</div>
        <div className="rounded-[24px] border border-white/10 bg-black/20 p-5">Healthy: {summary.healthy || 0}</div>
        <div className="rounded-[24px] border border-white/10 bg-black/20 p-5">Blocked: {summary.blocked || 0}</div>
        <div className="rounded-[24px] border border-white/10 bg-black/20 p-5">Dead: {summary.dead || 0}</div>
      </div>

      <section className="rounded-[24px] border border-white/10 bg-black/20 p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-xl font-semibold text-white">Book source health</h3>
          <div className="flex gap-3">
            <button
              className="rounded-xl border border-cyan-400/30 px-3 py-2 text-sm text-cyan-200"
              onClick={() => void load()}
            >
              Probe now
            </button>
            <Link to="/sources" className="text-sm text-cyan-300">
              Back to inventory
            </Link>
          </div>
        </div>

        {loading ? (
          <div className="text-sm text-zinc-400">Loading</div>
        ) : (
          <div className="space-y-4">
            {rows.map((row) => (
              <article key={row.source_id} className="rounded-2xl border border-white/8 bg-white/5 p-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h4 className="text-lg font-semibold text-white">{row.source_name}</h4>
                    <p className="text-sm text-zinc-400">{row.source_url}</p>
                    <p className={`mt-2 text-sm ${tone(row.health_status)}`}>health: {row.health_status}</p>
                    <p className="mt-1 text-sm text-zinc-300">
                      reason:{' '}
                      <span>{row.failure_reason || '-'}</span>
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="rounded-xl border border-cyan-400/30 px-3 py-2 text-sm text-cyan-200"
                      onClick={() => void handleProbe(row.source_id)}
                    >
                      Probe source
                    </button>
                    <button
                      className="rounded-xl border border-emerald-400/30 px-3 py-2 text-sm text-emerald-200"
                      onClick={() => void handleRecover(row.source_id)}
                    >
                      Recover
                    </button>
                  </div>
                </div>
                <div className="mt-4 grid gap-2 md:grid-cols-3">
                  <div className={`rounded-xl border border-white/10 p-3 text-sm ${tone(row.search_status)}`}>
                    search: {row.search_status}
                  </div>
                  <div className={`rounded-xl border border-white/10 p-3 text-sm ${tone(row.toc_status)}`}>
                    toc: {row.toc_status}
                  </div>
                  <div className={`rounded-xl border border-white/10 p-3 text-sm ${tone(row.content_status)}`}>
                    content: {row.content_status}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </ConsoleLayout>
  )
}
