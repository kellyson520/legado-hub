import { useState } from 'react'

import {
  getOperationAgentRun,
  listOperationAgentRuns,
  type OperationAgentRunDetail,
  type OperationAgentRunRow,
  type OperationAgentToolInvocationRow,
} from '@/api/modules/operations'
import { ListStatus } from '@/components/data/ListStatus'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { PaginationToolbar } from '@/components/data/PaginationToolbar'
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
  const pagination = useServerPagination<OperationAgentRunRow>({
    pageSize: 20,
    load: ({ page, pageSize, search }) => listOperationAgentRuns({ page, page_size: pageSize, search }),
  })
  const { rows, meta, loading, error: listError } = pagination
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
    <ConsoleLayout
      eyebrow="Operations"
      title="Agent runs"
      description="按租户查看最近 Agent run、工具调用结果与证据轨迹，用于回溯自动构建与知识处理过程。"
    >
      <div className="space-y-4">
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <PaginationToolbar
          page={meta.page}
          totalPages={meta.total_pages}
          total={meta.total}
          searchInput={pagination.searchInput}
          appliedSearch={pagination.appliedSearch}
          loading={loading}
          searchLabel="搜索 Agent run"
          onSearchInput={pagination.setSearchInput}
          onSearch={() => pagination.submitSearch()}
          onClearSearch={pagination.clearSearch}
          onPageChange={pagination.goToPage}
        />
        <ListStatus
          loading={loading}
          error={listError}
          empty={!loading && rows.length === 0}
          onRetry={pagination.retry}
          loadingLabel="正在加载 Agent runs…"
          errorLabel="Failed to load agent runs."
          emptyLabel="No agent runs yet"
        />
        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <table className="min-w-full divide-y divide-border text-sm">
            <thead className="bg-muted/40 text-left text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Run</th>
                <th className="px-4 py-3 font-medium">Tenant</th>
                <th className="px-4 py-3 font-medium">Summary</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((row) => {
                const inspecting = loadingDetail && selectedId === row.id
                return (
                  <tr key={row.id}>
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">{getAgentKind(row)}</div>
                      <div className="text-xs text-muted-foreground">{row.status}</div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{getTenantId(row)}</td>
                    <td className="px-4 py-3">
                      <div>
                        Tools {getToolInvocationCount(row)} · Accepted {getAcceptedCount(row)} · Rejected {getRejectedCount(row)}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Evidence {getEvidenceCount(row)} · Latest {getLatestToolName(row)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{getCreatedAt(row)}</td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-60"
                        onClick={() => void inspect(row.id)}
                        disabled={inspecting}
                        aria-label={`Inspect ${getAgentKind(row)} ${row.id}`}
                      >
                        {inspecting ? 'Loading…' : 'Inspect'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <section className="rounded-2xl border border-border bg-card p-4">
          <div className="mb-3">
            <h2 className="text-base font-semibold text-foreground">Run detail</h2>
            <p className="text-sm text-muted-foreground">
              {detail ? `${getAgentKind(detail)} · ${getTenantId(detail)}` : 'Select a run to inspect its tool history'}
            </p>
          </div>
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
                    Tools {getToolInvocationCount(detail)} · Accepted {getAcceptedCount(detail)} · Rejected {getRejectedCount(detail)}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Evidence {getEvidenceCount(detail)} · Latest {getLatestToolName(detail)}
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
                        Result {item.result?.status ?? 'pending'} · Evidence {getToolEvidence(item).length}
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
        </section>
      </div>
    </ConsoleLayout>
  )
}
