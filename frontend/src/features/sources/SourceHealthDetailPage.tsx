import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, RefreshCw, ShieldAlert } from 'lucide-react'

import { useLanguage } from '@/app/providers/LanguageProvider'
import {
  getSourceHealth,
  probeSourceHealth,
  recoverSourceHealth,
  type SourceHealthDetail,
  type SourceProbeRun,
  type SourceProbeStage,
} from '@/api/modules/sourceHealth'
import { AttemptTimeline } from '@/components/detail/AttemptTimeline'
import { DataTable, type DataTableColumn } from '@/components/data/DataTable'
import { EmptyState, ErrorState, LoadingState } from '@/components/data/ListStates'
import { StatusBadge } from '@/components/data/StatusBadge'
import { DetailPanel } from '@/components/detail/DetailPanel'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
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
  const { t } = useLanguage()
  const { sourceId } = useParams()
  const id = Number(sourceId)
  const [detail, setDetail] = useState<SourceHealthDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyAction, setBusyAction] = useState<'probe' | 'recover' | null>(null)

  async function load() {
    if (!Number.isInteger(id) || id <= 0) {
      setLoading(false)
      setError(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const response = await getSourceHealth(id)
      setDetail(response.data)
    } catch {
      setDetail(null)
      setError(t('Unable to load source health. Please try again.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [id])

  async function handleProbe() {
    setBusyAction('probe')
    try {
      await probeSourceHealth(id)
      await load()
    } catch {
      setError(t('Unable to load source health. Please try again.'))
    } finally {
      setBusyAction(null)
    }
  }

  async function handleRecover() {
    setBusyAction('recover')
    try {
      await recoverSourceHealth(id)
      await load()
    } catch {
      setError(t('Unable to load source health. Please try again.'))
    } finally {
      setBusyAction(null)
    }
  }

  const latestEvidence = useMemo(() => latestStageWithEvidence(detail?.runs || []), [detail])
  const snapshot = detail?.snapshot
  const latestKeywords = attemptedKeywords(detail?.runs?.[0])
  const historyColumns: DataTableColumn<SourceProbeRun>[] = [
    { id: 'time', header: t('Time'), cell: (run) => formatTime(run.created_at) },
    { id: 'result', header: t('Result'), cell: (run) => <StatusBadge status={run.overall_status} /> },
    { id: 'reason', header: t('Reason'), cell: (run) => run.failure_reason || '-' },
    { id: 'search', header: t('Search'), cell: (run) => <StatusBadge status={run.search_result.status} /> },
    { id: 'toc', header: t('TOC'), cell: (run) => <StatusBadge status={run.toc_result.status} /> },
    { id: 'content', header: t('Content'), cell: (run) => <StatusBadge status={run.content_result.status} /> },
  ]
  const failureTimelineItems = (detail?.failure_timeline ?? []).map((event, index) => ({
    id: `${event.at}-${event.stage}-${index}`,
    label: `${formatTime(event.at)} · ${event.stage} · ${event.reason}`,
    status: event.status || 'failed',
    detail: `${t('HTTP ')}${event.http_status ?? '-'} · ${event.response_kind || t('status.unknown')}${event.message ? ` · ${event.message}` : ''}`,
  }))

  return (
    <ConsolePageShell
      eyebrow="Source Health"
      title={snapshot ? snapshot.source_name : 'Source diagnostics'}
      description="Probe evidence, route decisions, and failure history for one source."
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
        <Link
          to="/sources/health"
          title={t('Back to health list')}
          aria-label={t('Back to health list')}
          className="inline-flex h-9 w-9 items-center justify-center border border-border text-foreground hover:border-primary hover:text-primary"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Link>
        <div className="flex items-center gap-2">
          <button
            type="button"
            title={t('Probe source')}
            aria-label={t('Probe source')}
            onClick={() => void handleProbe()}
            disabled={busyAction !== null}
            className="inline-flex h-9 w-9 items-center justify-center border border-primary/30 text-primary hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            title={t('Recover source')}
            aria-label={t('Recover source')}
            onClick={() => void handleRecover()}
            disabled={busyAction !== null}
            className="inline-flex h-9 w-9 items-center justify-center border border-emerald-500/30 text-emerald-600 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <ShieldAlert className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      {loading ? (
        <LoadingState label={t('Loading diagnostics')} />
      ) : error ? (
        <ErrorState label={error} onRetry={() => void load()} retryLabel={t('common.retry')} />
      ) : !detail ? (
        <EmptyState label={t('Source was not found')} />
      ) : (
        <div className="space-y-6">
          <DetailPanel
            title={t('Health')}
            items={[
              { label: t('Health'), value: snapshot?.failure_reason === 'not_probed' ? t('未探测') : <StatusBadge status={snapshot?.health_status ?? 'unknown'} /> },
              { label: t('Failure reason'), value: snapshot?.failure_reason || '-' },
              { label: t('Last probe'), value: formatTime(snapshot?.last_probe_at) },
              { label: t('Next probe'), value: formatTime(snapshot?.next_probe_at) },
            ]}
          />

          <DetailPanel
            title={t('Route decision')}
            items={[
              { label: t('Policy: '), value: detail.route_decision.policy },
              { label: t('Score: '), value: detail.route_decision.score },
              { label: t('Reason: '), value: detail.route_decision.reason },
            ]}
          >
            {latestKeywords.length ? <p className="text-sm text-muted-foreground">{t('尝试关键词：')}<span className="text-foreground">{latestKeywords.join('、')}</span></p> : null}
          </DetailPanel>

          <DetailPanel title={t('Request preview')} emptyLabel={t('No request preview')}>
            {latestEvidence ? (
              <div className="space-y-2 break-all font-mono text-xs text-muted-foreground">
                <p>{latestEvidence.request_preview || '-'}</p>
                <p>{String(latestEvidence.detail.response_preview || '-')}</p>
              </div>
            ) : null}
          </DetailPanel>

          <DetailPanel title={t('Probe history')} emptyLabel={t('No probe history')}>
            <DataTable rows={detail.runs} columns={historyColumns} getRowKey={(run) => run.id} emptyLabel={t('No probe history')} />
          </DetailPanel>

          <DetailPanel title={t('Failure timeline')} emptyLabel={t('No failed probe stages')}>
            {failureTimelineItems.length ? <AttemptTimeline items={failureTimelineItems} /> : null}
          </DetailPanel>
        </div>
      )}
    </ConsolePageShell>
  )
}
