import { listAuditLogs, type AuditLogRow } from '@/api/modules/admin'
import { PaginationToolbar } from '@/components/data/PaginationToolbar'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Card } from '@/components/ui/card'
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
      {error ? <Card className="flex items-center gap-3 p-4 text-sm text-destructive" role="alert"><span>Failed to load audit rows.</span><button type="button" className="underline" onClick={() => pagination.retry()}>重试</button></Card> : null}
      <div className="space-y-3">
        {!loading && logs.length === 0 ? (
          <div className="rounded-md border border-dashed border-border bg-muted/30 p-6 text-sm text-muted-foreground">
            No audit rows loaded yet.
          </div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className="rounded-md border border-border bg-card p-4 shadow-sm">
              <p className="text-sm font-medium text-foreground">
                {log.action} / {log.resource}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">{log.detail}</p>
            </div>
          ))
        )}
      </div>
    </ConsoleLayout>
  )
}
