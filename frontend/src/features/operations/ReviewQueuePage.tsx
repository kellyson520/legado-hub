import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { useLanguage } from '@/app/providers/LanguageProvider'
import {
  listReviewQueueCandidates,
  resolveReviewQueueItem,
  type OperationSourceBuildAuditSummary,
  type OperationReviewQueueRow,
} from '@/api/modules/operations'
import { DataTable, type DataTableColumn } from '@/components/data/DataTable'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { StatusMessage } from '@/components/data/StatusMessage'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { useServerPagination } from '@/hooks/useServerPagination'
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
  const { t } = useLanguage()
  const pagination = useServerPagination<OperationReviewQueueRow>({
    pageSize: 20,
    load: listReviewQueueCandidates,
  })
  const { rows } = pagination
  const [resolvedIds, setResolvedIds] = useState<Set<string>>(() => new Set())
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const visibleRows = useMemo(
    () => rows.filter((row) => !resolvedIds.has(row.id)),
    [resolvedIds, rows],
  )

  const columns: DataTableColumn<OperationReviewQueueRow>[] = [
    {
      id: 'type',
      header: t('Type'),
      cell: (row) => (
        <>
          <div className="font-medium text-foreground">{getProposalType(row)}</div>
          <div className="text-xs text-muted-foreground">{getItemType(row)} · {getSourceChapterId(row)}</div>
        </>
      ),
    },
    { id: 'work', header: t('Work'), cell: (row) => getWorkId(row) },
    {
      id: 'summary',
      header: t('Summary'),
      cell: (row) => (
        <>
          <div>{getSummary(row)}</div>
          <div className="text-xs text-muted-foreground">{row.subject || '-'} · {row.relation || '-'} · {getObjectName(row)}</div>
        </>
      ),
    },
    {
      id: 'evidence',
      header: t('Evidence'),
      cell: (row) => {
        const itemType = getItemType(row)
        const sourceAudit = ['source_version', 'source_review'].includes(itemType) ? getSourceAudit(row) : undefined
        return (
          <>
            <div>{row.evidence}</div>
            {sourceAudit ? <div className="mt-1"><SourceAuditSummary audit={sourceAudit} /></div> : null}
          </>
        )
      },
    },
    { id: 'created-by', header: t('Created by'), cell: (row) => <span className="text-muted-foreground">{getCreatedBy(row)}</span> },
    {
      id: 'action',
      header: t('Action'),
      cell: (row) => {
        const itemType = getItemType(row)
        const actionLabel = getActionLabel(row)
        const resolving = pendingId === row.id
        if (!canResolve(row)) return <span className="text-xs text-muted-foreground">{t('No action')}</span>
        return (
          <div className="flex flex-wrap gap-2">
            {itemType === 'source_version' ? (
              <Link to={`/sources/rules/${row.id}`} className="rounded-md border border-primary px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary hover:text-primary-foreground">
                审核规则
              </Link>
            ) : null}
            <button
              type="button"
              className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => void handleResolve(row)}
              disabled={resolving}
              aria-label={`${t(actionLabel)} ${getProposalType(row)}`}
            >
              {resolving ? t('Processing…') : t(actionLabel)}
            </button>
          </div>
        )
      },
    },
  ]

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
      setResolvedIds((current) => {
        const next = new Set(current)
        next.add(queueItemId)
        return next
      })
      setFeedback(`${getActionLabel(row)} completed for ${getProposalType(row)}`)
    } catch (resolveError) {
      const message = resolveError instanceof Error ? resolveError.message : 'Failed to resolve review item'
      setError(message)
    } finally {
      setPendingId(null)
    }
  }

  return (
    <ConsolePageShell
      eyebrow="Operations"
      title="Review queue"
      description="聚合低置信度对齐、自动修复阻断与人工审核入口，当前承载 work knowledge、translation review 与 source version publish 候选项。"
    >
      <div className="space-y-3">
        <StatusMessage tone="success" message={feedback} />
        <StatusMessage tone="error" message={error} />
        <PaginatedListControls
          pagination={pagination}
          empty={false}
          loadingLabel="正在加载审核队列…"
          errorLabel="Failed to load review queue."
          emptyLabel="No review candidates yet"
          searchLabel="搜索审核项"
        />
        <DataTable rows={visibleRows} columns={columns} getRowKey={(row) => row.id} emptyLabel={t('No review candidates yet')} />
      </div>
    </ConsolePageShell>
  )
}
