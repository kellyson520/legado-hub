import { useState } from 'react'

import { useLanguage } from '@/app/providers/LanguageProvider'
import {
  listSourceBuildCandidates,
  type OperationSourceBuildAuditSummary,
  type OperationSourceBuildRow,
} from '@/api/modules/operations'
import { DataTable, type DataTableColumn } from '@/components/data/DataTable'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { StatusBadge } from '@/components/data/StatusBadge'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { Button } from '@/components/ui/button'
import { useServerPagination } from '@/hooks/useServerPagination'
import { ManualVerificationPanel } from './ManualVerificationPanel'

function getSourceId(row: OperationSourceBuildRow) {
  return row.sourceId ?? row.source_id ?? row.payload.canonical_url ?? '-'
}

function getLatestRun(row: OperationSourceBuildRow) {
  return row.latestRun ?? row.latest_run ?? null
}

function getCreatedBy(row: OperationSourceBuildRow) {
  return row.createdBy ?? row.created_by ?? row.payload.submitted_by ?? '-'
}

function getAutonomousBuild(row: OperationSourceBuildRow) {
  return row.payload.autonomousBuild ?? row.payload.autonomous_build
}

function getSourceAudit(row: OperationSourceBuildRow) {
  return row.payload.sourceAudit ?? row.payload.source_audit
}

function getAuditStatus(audit: OperationSourceBuildAuditSummary) {
  return audit.status ?? audit.report?.status ?? 'pending'
}

function getAuditAttempt(audit: OperationSourceBuildAuditSummary) {
  return audit.attempt ?? audit.report?.attempt ?? 0
}

function getAuditMaxAttempts(audit: OperationSourceBuildAuditSummary) {
  return audit.maxAttempts ?? audit.max_attempts ?? audit.report?.maxAttempts ?? audit.report?.max_attempts ?? 5
}

function getAuditGrade(audit: OperationSourceBuildAuditSummary) {
  return audit.grade ?? audit.report?.grade ?? '-'
}

function getAuditTotalElapsedMs(audit: OperationSourceBuildAuditSummary) {
  return audit.report?.totalElapsedMs ?? audit.report?.total_elapsed_ms
}

export function SourceAuditSummary({ audit }: { audit?: OperationSourceBuildAuditSummary }) {
  const { t } = useLanguage()
  if (!audit) return <span className="text-muted-foreground">-</span>

  const status = getAuditStatus(audit)
  const report = audit.report
  const totalElapsedMs = getAuditTotalElapsedMs(audit)
  const terminalFailure = status === 'failed'
  const summary = (
    <>
      <div className={terminalFailure ? 'font-medium text-destructive' : 'font-medium text-foreground'}>
        {t('Audit: ')}{t(status)} · {getAuditAttempt(audit)}/{getAuditMaxAttempts(audit)} · {getAuditGrade(audit)}
      </div>
      {report?.stages ? (
        <div className="text-muted-foreground">
          {t('search/toc/content: ')}{t(report.stages.search?.status ?? '-')} / {t(report.stages.toc?.status ?? '-')} /{' '}
          {t(report.stages.content?.status ?? '-')}
          {typeof totalElapsedMs === 'number' ? ` · ${totalElapsedMs}ms` : ''}
        </div>
      ) : null}
      {typeof totalElapsedMs === 'number' ? <div className="text-muted-foreground">{t('total parse: ')}{totalElapsedMs}ms</div> : null}
      {report?.reason ? <div className="text-muted-foreground">{report.reason}</div> : null}
    </>
  )

  return terminalFailure ? (
    <div className="space-y-1 text-xs leading-5" role="alert">
      {summary}
    </div>
  ) : (
    <div className="space-y-1 text-xs leading-5">{summary}</div>
  )
}

export function SourceBuildsPage() {
  const pagination = useServerPagination<OperationSourceBuildRow>({
    pageSize: 20,
    load: listSourceBuildCandidates,
  })
  const { rows } = pagination
  const [verificationSessionId, setVerificationSessionId] = useState<string | null>(null)
  const { t } = useLanguage()
  const columns: DataTableColumn<OperationSourceBuildRow>[] = [
    {
      id: 'source',
      header: t('Source'),
      cell: (row) => <><div className="font-medium text-foreground">{getSourceId(row)}</div><div className="text-xs text-muted-foreground">{row.id}</div></>,
    },
    { id: 'keyword', header: t('Keyword'), cell: (row) => row.payload.keyword || '-' },
    { id: 'status', header: t('Status'), cell: (row) => <StatusBadge status={row.status} /> },
    { id: 'grade', header: t('Latest grade'), cell: (row) => getLatestRun(row)?.grade ?? '-' },
    {
      id: 'audit',
      header: t('Audit'),
      cell: (row) => {
        const sourceAudit = getSourceAudit(row)
        const sessionId = sourceAudit?.browser_session_id ?? sourceAudit?.browserSessionId
        return (
          <>
            <SourceAuditSummary audit={sourceAudit} />
            {getAuditStatus(sourceAudit ?? {}) === 'awaiting_manual_verification' ? (
              <Button type="button" variant="link" size="sm" className="mt-1 h-auto px-0 text-xs" onClick={() => setVerificationSessionId(sessionId ?? null)} disabled={!sessionId}>
                {t('Open manual verification')}
              </Button>
            ) : null}
          </>
        )
      },
    },
    {
      id: 'automation',
      header: t('Automation'),
      cell: (row) => {
        const autonomousBuild = getAutonomousBuild(row)
        if (!autonomousBuild) return <span className="text-muted-foreground">-</span>
        return (
          <>
            <div>{autonomousBuild.decision ?? '-'}</div>
            <div className="text-xs text-muted-foreground">{autonomousBuild.trigger ?? '-'} 路 {autonomousBuild.strategy ?? '-'}</div>
            {autonomousBuild.validation ? <div className="text-xs text-muted-foreground">{t('validation: ')}{autonomousBuild.validation.grade ?? '-'} ({autonomousBuild.validation.quality_score ?? '-'})</div> : null}
            {autonomousBuild.probe ? <>
              <div className="text-xs text-muted-foreground">{t('search/toc/content: ')}{t(autonomousBuild.probe.search_status ?? '-')} / {t(autonomousBuild.probe.toc_status ?? '-')} / {t(autonomousBuild.probe.content_status ?? '-')}</div>
              <div className="text-xs text-muted-foreground">{autonomousBuild.probe.sample_title ?? autonomousBuild.probe.failure_reason ?? '-'}</div>
            </> : null}
          </>
        )
      },
    },
    { id: 'created-by', header: t('Submitted by'), cell: (row) => <span className="text-muted-foreground">{getCreatedBy(row)}</span> },
  ]

  return (
    <ConsolePageShell
      eyebrow="Operations"
      title="Source build candidates"
      description="查看候选 source build、最近验证结果与自动修补探针摘要。"
    >
      <PaginatedListControls
        pagination={pagination}
        empty={false}
        loadingLabel="正在加载构建候选…"
        errorLabel="Failed to load source build candidates."
        emptyLabel="No source build candidates yet"
        searchLabel="搜索构建候选"
      />
      <DataTable rows={rows} columns={columns} getRowKey={(row) => row.id} emptyLabel={t('No source build candidates yet')} />
      {verificationSessionId ? (
        <ManualVerificationPanel sessionId={verificationSessionId} onFinished={() => setVerificationSessionId(null)} />
      ) : null}
    </ConsolePageShell>
  )
}
