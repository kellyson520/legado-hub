import { listAuditLogs, type AuditLogRow } from '@/api/modules/admin'
import { ListStatus } from '@/components/data/ListStatus'
import { PaginationToolbar } from '@/components/data/PaginationToolbar'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { useServerPagination } from '@/hooks/useServerPagination'

export function AdminAuditPage() {
  const pagination = useServerPagination<AuditLogRow>({
    pageSize: 50,
    load: ({ page, pageSize, search }) => listAuditLogs({ page, page_size: pageSize, search }),
  })
  const { rows: logs, meta, loading, error } = pagination

  return (
    <ConsoleLayout
      eyebrow="Audit"
      title="Operational trace ledger"
      description="把高风险操作与自动化动作都纳入统一审计视图，便于排查部署、回滚、授权与任务执行链路。"
    >
      <PaginationToolbar
        page={meta.page}
        totalPages={meta.total_pages}
        total={meta.total}
        searchInput={pagination.searchInput}
        appliedSearch={pagination.appliedSearch}
        loading={loading}
        searchLabel="搜索审计"
        onSearchInput={pagination.setSearchInput}
        onSearch={() => pagination.submitSearch()}
        onClearSearch={pagination.clearSearch}
        onPageChange={pagination.goToPage}
      />
      <ListStatus
        loading={loading}
        error={error}
        empty={!loading && logs.length === 0}
        onRetry={pagination.retry}
        loadingLabel="正在加载审计记录…"
        errorLabel="Failed to load audit rows."
        emptyLabel="No audit rows loaded yet."
      />
      <div className="space-y-3">
        {logs.map((log) => (
            <div key={log.id} className="rounded-md border border-border bg-card p-4 shadow-sm">
              <p className="text-sm font-medium text-foreground">
                {log.action} / {log.resource}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">{log.detail}</p>
            </div>
        ))}
      </div>
    </ConsoleLayout>
  )
}
