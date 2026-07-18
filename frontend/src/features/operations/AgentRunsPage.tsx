import { useState } from 'react'

import { useLanguage } from '@/app/providers/LanguageProvider'
import {
  getOperationAgentRun,
  listOperationAgentRuns,
  type OperationAgentRunDetail,
  type OperationAgentRunRow,
  type OperationAgentToolInvocationRow,
} from '@/api/modules/operations'
import { DataTable } from '@/components/data/DataTable'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { StatusBadge } from '@/components/data/StatusBadge'
import { StatusMessage } from '@/components/data/StatusMessage'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { SectionHeader } from '@/components/layout/SectionHeader'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useServerPagination } from '@/hooks/useServerPagination'

function getAgentKind(row: OperationAgentRunRow | OperationAgentRunDetail) {
  return row.agentKind ?? row.agent_kind ?? 'agent'
}

function getTenantId(row: OperationAgentRunRow | OperationAgentRunDetail) {
  return row.tenantId ?? row.tenant_id ?? '-'
}

function getCreatedAt(row: OperationAgentRunRow | OperationAgentRunDetail) {
  return row.createdAt ?? row.created_at ?? '-'
}

function getToolInvocationCount(row: OperationAgentRunRow | OperationAgentRunDetail) {
  return row.toolInvocationCount ?? row.tool_invocation_count ?? 0
}

function getAcceptedCount(row: OperationAgentRunRow | OperationAgentRunDetail) {
  return row.acceptedCount ?? row.accepted_count ?? 0
}

function getRejectedCount(row: OperationAgentRunRow | OperationAgentRunDetail) {
  return row.rejectedCount ?? row.rejected_count ?? 0
}

function getEvidenceCount(row: OperationAgentRunRow | OperationAgentRunDetail) {
  return row.evidenceCount ?? row.evidence_count ?? 0
}

function getLatestToolName(row: OperationAgentRunRow | OperationAgentRunDetail) {
  return row.latestToolName ?? row.latest_tool_name ?? '-'
}

function getToolName(row: OperationAgentToolInvocationRow) {
  return row.toolName ?? row.tool_name ?? 'tool'
}

function getToolEvidence(row: OperationAgentToolInvocationRow) {
  return row.evidence ?? []
}

function getToolHistory(detail: OperationAgentRunDetail | null) {
  return detail?.toolHistory ?? detail?.tool_history ?? []
}

function formatPayload(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2)
}

export function AgentRunsPage() {
  const { t } = useLanguage()
  const pagination = useServerPagination<OperationAgentRunRow>({
    pageSize: 20,
    load: listOperationAgentRuns,
  })
  const { rows } = pagination
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<OperationAgentRunDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function inspect(runId: string) {
    setSelectedId(runId)
    setLoadingDetail(true)
    setError(null)
    try {
      const response = await getOperationAgentRun(runId)
      setDetail(response.data)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load agent run detail')
    } finally {
      setLoadingDetail(false)
    }
  }

  return (
    <ConsolePageShell
      eyebrow="Operations"
      title="Agent runs"
      description="按租户查看最近 Agent run、工具调用结果与证据轨迹，用于回溯自动构建与知识处理过程。"
    >
      <div className="space-y-4">
        <StatusMessage tone="error" message={error} />
        <PaginatedListControls
          pagination={pagination}
          empty={!pagination.loading && rows.length === 0}
          loadingLabel="正在加载 Agent runs…"
          errorLabel="Failed to load agent runs."
          emptyLabel="No agent runs yet"
          searchLabel="搜索 Agent run"
        />
        <DataTable
          rows={rows}
          getRowKey={(row) => row.id}
          columns={[
            {
              id: 'run',
              header: t('Run'),
              cell: (row) => <div className="space-y-1"><div className="font-medium text-foreground">{getAgentKind(row)}</div><StatusBadge status={row.status} /></div>,
            },
            { id: 'tenant', header: t('Tenant'), cell: (row) => <span className="text-muted-foreground">{getTenantId(row)}</span> },
            {
              id: 'summary',
              header: t('Summary'),
              cell: (row) => <><div>{t('Tools ')}{getToolInvocationCount(row)} · {t('Accepted ')}{getAcceptedCount(row)} · {t('Rejected ')}{getRejectedCount(row)}</div><div className="text-xs text-muted-foreground">{t('Evidence ')}{getEvidenceCount(row)} · {t('Latest ')}{getLatestToolName(row)}</div></>,
            },
            { id: 'created', header: t('Created'), cell: (row) => <span className="text-muted-foreground">{getCreatedAt(row)}</span> },
            {
              id: 'action',
              header: t('Action'),
              cell: (row) => {
                const inspecting = loadingDetail && selectedId === row.id
                return <Button type="button" variant="outline" size="sm" onClick={() => void inspect(row.id)} disabled={inspecting} aria-label={`${t('Inspect')} ${getAgentKind(row)} ${row.id}`}>{inspecting ? t('Loading…') : t('Inspect')}</Button>
              },
            },
          ]}
        />

        <Card className="p-4">
          <SectionHeader title="Run detail" description={detail ? `${getAgentKind(detail)} · ${getTenantId(detail)}` : 'Select a run to inspect its tool history'} className="mb-3" />
          {detail ? (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-border bg-muted/20 p-3">
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">Input payload</div>
                  <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs text-foreground">
                    {formatPayload(detail.inputPayload ?? detail.input_payload)}
                  </pre>
                </div>
                <div className="rounded-xl border border-border bg-muted/20 p-3">
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">Summary</div>
                  <div className="mt-2 text-sm text-foreground">
                    {t('Tools ')}{getToolInvocationCount(detail)} · {t('Accepted ')}{getAcceptedCount(detail)} · {t('Rejected ')}{getRejectedCount(detail)}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {t('Evidence ')}{getEvidenceCount(detail)} · {t('Latest ')}{getLatestToolName(detail)}
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                {getToolHistory(detail).map((item) => (
                  <article key={item.id} className="rounded-xl border border-border bg-muted/20 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div className="font-medium text-foreground">{getToolName(item)}</div>
                        <div className="text-xs text-muted-foreground">
                          {item.category} · {item.createdAt ?? item.created_at ?? '-'}
                        </div>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {t('Result ')}{t(item.result?.status ?? 'pending')} · {t('Evidence ')}{getToolEvidence(item).length}
                      </div>
                    </div>
                    <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs text-foreground">
                      {formatPayload(item.arguments)}
                    </pre>
                    {item.result ? (
                      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs text-foreground">
                        {formatPayload(item.result.data)}
                      </pre>
                    ) : null}
                    {getToolEvidence(item).length > 0 ? (
                      <ul className="mt-3 space-y-2 text-xs text-muted-foreground">
                        {getToolEvidence(item).map((evidence) => (
                          <li key={evidence.id}>
                            {(evidence.evidenceType ?? evidence.evidence_type) || 'evidence'} ·{' '}
                            {(evidence.resourceId ?? evidence.resource_id) || '-'}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </article>
                ))}
                {getToolHistory(detail).length === 0 ? (
                  <p className="text-sm text-muted-foreground">No tool history recorded for this run</p>
                ) : null}
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Select a run to inspect its tool history</p>
          )}
        </Card>
      </div>
    </ConsolePageShell>
  )
}
