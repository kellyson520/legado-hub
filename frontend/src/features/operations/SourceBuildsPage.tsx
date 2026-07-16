import { useState } from 'react'

import {
  listSourceBuildCandidates,
  type OperationSourceBuildAuditSummary,
  type OperationSourceBuildRow,
} from '@/api/modules/operations'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { useServerPagination } from '@/hooks/useServerPagination'
import { toPaginatedQueryParams } from '@/lib/pagination'
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
  if (!audit) return <span className="text-muted-foreground">-</span>

  const status = getAuditStatus(audit)
  const report = audit.report
  const totalElapsedMs = getAuditTotalElapsedMs(audit)
  const terminalFailure = status === 'failed'
  const summary = (
    <>
      <div className={terminalFailure ? 'font-medium text-destructive' : 'font-medium text-foreground'}>
        Audit: {status} · {getAuditAttempt(audit)}/{getAuditMaxAttempts(audit)} · {getAuditGrade(audit)}
      </div>
      {report?.stages ? (
        <div className="text-muted-foreground">
          search/toc/content: {report.stages.search?.status ?? '-'} / {report.stages.toc?.status ?? '-'} /{' '}
          {report.stages.content?.status ?? '-'}
          {typeof totalElapsedMs === 'number' ? ` · ${totalElapsedMs}ms` : ''}
        </div>
      ) : null}
      {typeof totalElapsedMs === 'number' ? <div className="text-muted-foreground">total parse: {totalElapsedMs}ms</div> : null}
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
    load: (request) => listSourceBuildCandidates(toPaginatedQueryParams(request)),
  })
  const { rows } = pagination
  const [verificationSessionId, setVerificationSessionId] = useState<string | null>(null)

  return (
    <ConsoleLayout
      eyebrow="Operations"
      title="Source build candidates"
      description="查看候选 source build、最近验证结果与自动修补探针摘要。"
    >
      <PaginatedListControls
        pagination={pagination}
        empty={!pagination.loading && rows.length === 0}
        loadingLabel="正在加载构建候选…"
        errorLabel="Failed to load source build candidates."
        emptyLabel="No source build candidates yet"
        searchLabel="搜索构建候选"
      />
      <div className="overflow-hidden rounded-2xl border border-border bg-card">
        <table className="min-w-full divide-y divide-border text-sm">
          <thead className="bg-muted/40 text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Source</th>
              <th className="px-4 py-3 font-medium">Keyword</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Latest grade</th>
              <th className="px-4 py-3 font-medium">Audit</th>
              <th className="px-4 py-3 font-medium">Automation</th>
              <th className="px-4 py-3 font-medium">Submitted by</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => {
              const latestRun = getLatestRun(row)
              const autonomousBuild = getAutonomousBuild(row)
              const sourceAudit = getSourceAudit(row)
              return (
                <tr key={row.id}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-foreground">{getSourceId(row)}</div>
                    <div className="text-xs text-muted-foreground">{row.id}</div>
                  </td>
                  <td className="px-4 py-3">{row.payload.keyword || '-'}</td>
                  <td className="px-4 py-3">{row.status}</td>
                  <td className="px-4 py-3">{latestRun?.grade ?? '-'}</td>
                  <td className="px-4 py-3">
                    <SourceAuditSummary audit={sourceAudit} />
                    {getAuditStatus(sourceAudit ?? {}) === 'awaiting_manual_verification' ? (
                      <button
                        type="button"
                        className="mt-2 text-xs font-medium text-primary underline"
                        onClick={() => setVerificationSessionId(sourceAudit?.browser_session_id ?? sourceAudit?.browserSessionId ?? null)}
                        disabled={!sourceAudit?.browser_session_id && !sourceAudit?.browserSessionId}
                      >
                        Open manual verification
                      </button>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    {autonomousBuild ? (
                      <>
                        <div>{autonomousBuild.decision ?? '-'}</div>
                        <div className="text-xs text-muted-foreground">
                          {autonomousBuild.trigger ?? '-'} 路 {autonomousBuild.strategy ?? '-'}
                        </div>
                        {autonomousBuild.validation ? (
                          <div className="text-xs text-muted-foreground">
                            validation: {autonomousBuild.validation.grade ?? '-'} (
                            {autonomousBuild.validation.quality_score ?? '-'}
                            )
                          </div>
                        ) : null}
                        {autonomousBuild.probe ? (
                          <>
                            <div className="text-xs text-muted-foreground">
                              search/toc/content: {autonomousBuild.probe.search_status ?? '-'} /{' '}
                              {autonomousBuild.probe.toc_status ?? '-'} / {autonomousBuild.probe.content_status ?? '-'}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {autonomousBuild.probe.sample_title ??
                                autonomousBuild.probe.failure_reason ??
                                '-'}
                            </div>
                          </>
                        ) : null}
                      </>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{getCreatedBy(row)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {verificationSessionId ? (
        <ManualVerificationPanel sessionId={verificationSessionId} onFinished={() => setVerificationSessionId(null)} />
      ) : null}
    </ConsoleLayout>
  )
}
