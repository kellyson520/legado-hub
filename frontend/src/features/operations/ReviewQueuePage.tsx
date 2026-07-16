import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  listReviewQueueCandidates,
  resolveReviewQueueItem,
  type OperationSourceBuildAuditSummary,
  type OperationReviewQueueRow,
} from '@/api/modules/operations'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { SourceAuditSummary } from './SourceBuildsPage'

function getProposalType(row: OperationReviewQueueRow) {
  return row.proposalType ?? row.proposal_type ?? '-'
}

function getItemType(row: OperationReviewQueueRow) {
  return row.itemType ?? row.item_type ?? 'review_item'
}

function getWorkId(row: OperationReviewQueueRow) {
  return row.workId ?? row.work_id ?? '-'
}

function getSourceChapterId(row: OperationReviewQueueRow) {
  return row.sourceChapterId ?? row.source_chapter_id ?? '-'
}

function getObjectName(row: OperationReviewQueueRow) {
  return row.objectName ?? row.object_name ?? '-'
}

function getCreatedBy(row: OperationReviewQueueRow) {
  return row.createdBy ?? row.created_by ?? '-'
}

function getSummary(row: OperationReviewQueueRow) {
  if (row.summary) return row.summary
  const subject = row.subject || '-'
  const relation = row.relation || '-'
  const objectName = getObjectName(row)
  return `${subject} -> ${relation} -> ${objectName}`
}

function getSourceAudit(row: OperationReviewQueueRow): OperationSourceBuildAuditSummary | undefined {
  const payload = row.payload
  if (!payload) return undefined
  const sourceAudit = payload.sourceAudit ?? payload.source_audit
  if (sourceAudit) return sourceAudit

  const auditReport = payload.auditReport ?? payload.audit_report
  if (!auditReport) return undefined
  return {
    status: auditReport.status,
    attempt: auditReport.attempt,
    max_attempts: auditReport.max_attempts,
    maxAttempts: auditReport.maxAttempts,
    score: auditReport.score,
    grade: auditReport.grade,
    test_run_pending: auditReport.test_run_pending,
    testRunPending: auditReport.testRunPending,
    report: auditReport,
  }
}

function getActionLabel(row: OperationReviewQueueRow) {
  const itemType = getItemType(row)
  if (itemType === 'translation_job') return 'Mark reviewed'
  if (itemType === 'source_review') return 'Resolve'
  return 'Publish'
}

function canResolve(row: OperationReviewQueueRow) {
  return ['knowledge_proposal', 'source_version', 'source_review', 'translation_job'].includes(getItemType(row))
}

export function ReviewQueuePage() {
  const [rows, setRows] = useState<OperationReviewQueueRow[]>([])
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true

    async function load() {
      const response = await listReviewQueueCandidates()
      if (!mounted) return
      setRows(response.data)
    }

    void load()
    return () => {
      mounted = false
    }
  }, [])

  async function handleResolve(row: OperationReviewQueueRow) {
    const itemType = getItemType(row)
    setPendingId(row.id)
    setError(null)
    setFeedback(null)
    try {
      const response = await resolveReviewQueueItem(row.id, {
        itemType,
        action:
          itemType === 'translation_job'
            ? 'review'
            : itemType === 'source_review'
              ? 'resolve'
              : 'publish',
        memoryNote:
          itemType === 'translation_job'
            ? {
                source: 'operations.review_queue',
                proposal_type: getProposalType(row),
              }
            : undefined,
      })
      const queueItemId = response.data.queueItemId ?? response.data.queue_item_id ?? row.id
      setRows((current) => current.filter((item) => item.id !== queueItemId))
      setFeedback(`${getActionLabel(row)} completed for ${getProposalType(row)}`)
    } catch (resolveError) {
      const message = resolveError instanceof Error ? resolveError.message : 'Failed to resolve review item'
      setError(message)
    } finally {
      setPendingId(null)
    }
  }

  return (
    <ConsoleLayout
      eyebrow="Operations"
      title="Review queue"
      description="聚合低置信度对齐、自动修复阻断与人工审核入口，当前承载 work knowledge、translation review 与 source version publish 候选项。"
    >
      <div className="space-y-3">
        {feedback ? <p className="text-sm text-emerald-600">{feedback}</p> : null}
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <table className="min-w-full divide-y divide-border text-sm">
            <thead className="bg-muted/40 text-left text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Work</th>
                <th className="px-4 py-3 font-medium">Summary</th>
                <th className="px-4 py-3 font-medium">Evidence</th>
                <th className="px-4 py-3 font-medium">Created by</th>
                <th className="px-4 py-3 font-medium">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((row) => {
                const itemType = getItemType(row)
                const actionLabel = getActionLabel(row)
                const resolving = pendingId === row.id
                const sourceAudit = ['source_version', 'source_review'].includes(itemType)
                  ? getSourceAudit(row)
                  : undefined
                return (
                  <tr key={row.id}>
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">{getProposalType(row)}</div>
                      <div className="text-xs text-muted-foreground">
                        {itemType} · {getSourceChapterId(row)}
                      </div>
                    </td>
                    <td className="px-4 py-3">{getWorkId(row)}</td>
                    <td className="px-4 py-3">
                      <div>{getSummary(row)}</div>
                      <div className="text-xs text-muted-foreground">
                        {row.subject || '-'} · {row.relation || '-'} · {getObjectName(row)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      <div>{row.evidence}</div>
                      {sourceAudit ? (
                        <div className="mt-1">
                          <SourceAuditSummary audit={sourceAudit} />
                        </div>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{getCreatedBy(row)}</td>
                    <td className="px-4 py-3">
                      {canResolve(row) ? (
                        <div className="flex flex-wrap gap-2">
                          {itemType === 'source_version' ? (
                            <Link
                              to={`/sources/rules/${row.id}`}
                              className="rounded-lg border border-primary px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary hover:text-primary-foreground"
                            >
                              审核规则
                            </Link>
                          ) : null}
                          <button
                            type="button"
                            className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-60"
                            onClick={() => void handleResolve(row)}
                            disabled={resolving}
                            aria-label={`${actionLabel} ${getProposalType(row)}`}
                          >
                            {resolving ? 'Processing…' : actionLabel}
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">No action</span>
                      )}
                    </td>
                  </tr>
                )
              })}
              {rows.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-muted-foreground" colSpan={6}>
                    No review candidates yet
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </ConsoleLayout>
  )
}
