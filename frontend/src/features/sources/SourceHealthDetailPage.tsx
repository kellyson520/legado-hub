import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, RefreshCw, ShieldAlert } from 'lucide-react'

import {
  getSourceHealth,
  probeSourceHealth,
  recoverSourceHealth,
  type SourceHealthDetail,
  type SourceProbeRun,
  type SourceProbeStage,
} from '@/api/modules/sourceHealth'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function stageTone(status: string) {
  if (status === 'ok' || status === 'healthy') return 'text-emerald-300'
  if (status === 'failed' || status === 'blocked' || status === 'dead') return 'text-rose-300'
  if (status === 'degraded') return 'text-amber-300'
  return 'text-zinc-400'
}

function latestStageWithEvidence(runs: SourceProbeRun[]): SourceProbeStage | null {
  for (const run of runs) {
    for (const stage of [run.search_result, run.toc_result, run.content_result]) {
      if (stage.request_preview || stage.detail.response_preview) return stage
    }
  }
  return null
}

function attemptedKeywords(run: SourceProbeRun | undefined): string[] {
  const values = run?.summary?.attempted_keywords
  return Array.isArray(values) ? values.filter((value): value is string => typeof value === 'string' && value.length > 0) : []
}

export function SourceHealthDetailPage() {
  const { sourceId } = useParams()
  const id = Number(sourceId)
  const [detail, setDetail] = useState<SourceHealthDetail | null>(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    if (!Number.isInteger(id) || id <= 0) {
      setLoading(false)
      return
    }
    const response = await getSourceHealth(id)
    setDetail(response.data)
    setLoading(false)
  }

  useEffect(() => {
    void load()
  }, [id])

  async function handleProbe() {
    await probeSourceHealth(id)
    await load()
  }

  async function handleRecover() {
    await recoverSourceHealth(id)
    await load()
  }

  const latestEvidence = useMemo(() => latestStageWithEvidence(detail?.runs || []), [detail])
  const snapshot = detail?.snapshot
  const latestKeywords = attemptedKeywords(detail?.runs?.[0])

  return (
    <ConsoleLayout
      eyebrow="Source Health"
      title={snapshot ? snapshot.source_name : 'Source diagnostics'}
      description="Probe evidence, route decisions, and failure history for one source."
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
        <Link
          to="/sources/health"
          title="Back to health list"
          aria-label="Back to health list"
          className="inline-flex h-9 w-9 items-center justify-center border border-white/15 text-zinc-200 hover:border-cyan-300 hover:text-cyan-200"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Link>
        <div className="flex items-center gap-2">
          <button
            type="button"
            title="Probe source"
            aria-label="Probe source"
            onClick={() => void handleProbe()}
            className="inline-flex h-9 w-9 items-center justify-center border border-cyan-400/30 text-cyan-200 hover:bg-cyan-400/10"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            title="Recover source"
            aria-label="Recover source"
            onClick={() => void handleRecover()}
            className="inline-flex h-9 w-9 items-center justify-center border border-emerald-400/30 text-emerald-200 hover:bg-emerald-400/10"
          >
            <ShieldAlert className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-zinc-400">Loading diagnostics</p>
      ) : !detail ? (
        <p className="text-sm text-zinc-400">Source was not found</p>
      ) : (
        <div className="space-y-6">
          <section className="grid gap-4 border border-white/10 p-4 md:grid-cols-4">
            <div>
              <p className="text-xs text-zinc-500">Health</p>
              <p className={`mt-1 text-sm font-medium ${stageTone(snapshot?.health_status || 'unknown')}`}>
                {snapshot?.failure_reason === 'not_probed' ? '未探测' : (snapshot?.health_status || 'unknown')}
              </p>
            </div>
            <div>
              <p className="text-xs text-zinc-500">Failure reason</p>
              <p className="mt-1 text-sm text-zinc-100">{snapshot?.failure_reason || '-'}</p>
            </div>
            <div>
              <p className="text-xs text-zinc-500">Last probe</p>
              <p className="mt-1 text-sm text-zinc-100">{formatTime(snapshot?.last_probe_at)}</p>
            </div>
            <div>
              <p className="text-xs text-zinc-500">Next probe</p>
              <p className="mt-1 text-sm text-zinc-100">{formatTime(snapshot?.next_probe_at)}</p>
            </div>
          </section>

          <section className="border border-white/10 p-4">
            <h3 className="text-base font-semibold text-white">Route decision</h3>
            <div className="mt-3 grid gap-3 text-sm md:grid-cols-3">
              <p className="text-zinc-300">Policy: <span className="text-white">{detail.route_decision.policy}</span></p>
              <p className="text-zinc-300">Score: <span className="text-white">{detail.route_decision.score}</span></p>
              <p className="text-zinc-300">Reason: <span className="text-white">{detail.route_decision.reason}</span></p>
            </div>
            {latestKeywords.length ? <p className="mt-3 text-sm text-zinc-300">尝试关键词：<span className="text-white">{latestKeywords.join('、')}</span></p> : null}
          </section>

          <section className="border border-white/10 p-4">
            <h3 className="text-base font-semibold text-white">Request preview</h3>
            {latestEvidence ? (
              <div className="mt-3 space-y-2 break-all font-mono text-xs text-zinc-300">
                <p>{latestEvidence.request_preview || '-'}</p>
                <p>{String(latestEvidence.detail.response_preview || '-')}</p>
              </div>
            ) : (
              <p className="mt-3 text-sm text-zinc-400">No request preview</p>
            )}
          </section>

          <section className="border border-white/10 p-4">
            <h3 className="text-base font-semibold text-white">Probe history</h3>
            {detail.runs.length === 0 ? (
              <p className="mt-3 text-sm text-zinc-400">No probe history</p>
            ) : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[680px] text-left text-sm">
                  <thead className="border-b border-white/10 text-xs text-zinc-500">
                    <tr><th className="p-2">Time</th><th className="p-2">Result</th><th className="p-2">Reason</th><th className="p-2">Search</th><th className="p-2">TOC</th><th className="p-2">Content</th></tr>
                  </thead>
                  <tbody>
                    {detail.runs.map((run) => (
                      <tr key={run.id} className="border-b border-white/5 text-zinc-300">
                        <td className="p-2">{formatTime(run.created_at)}</td>
                        <td className={`p-2 ${stageTone(run.overall_status)}`}>{run.overall_status}</td>
                        <td className="p-2">{run.failure_reason || '-'}</td>
                        <td className={`p-2 ${stageTone(run.search_result.status)}`}>{run.search_result.status}</td>
                        <td className={`p-2 ${stageTone(run.toc_result.status)}`}>{run.toc_result.status}</td>
                        <td className={`p-2 ${stageTone(run.content_result.status)}`}>{run.content_result.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="border border-white/10 p-4">
            <h3 className="text-base font-semibold text-white">Failure timeline</h3>
            {detail.failure_timeline.length === 0 ? (
              <p className="mt-3 text-sm text-zinc-400">No failed probe stages</p>
            ) : (
              <ol className="mt-3 space-y-3 border-l border-white/15 pl-4">
                {detail.failure_timeline.map((event, index) => (
                  <li key={`${event.at}-${event.stage}-${index}`} className="text-sm">
                    <p className="text-zinc-200">{formatTime(event.at)} · {event.stage} · {event.reason}</p>
                    <p className="mt-1 text-xs text-zinc-500">HTTP {event.http_status ?? '-'} · {event.response_kind || 'unknown'} {event.message ? `· ${event.message}` : ''}</p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      )}
    </ConsoleLayout>
  )
}
