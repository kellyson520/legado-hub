import { listOperationsJobs, type OperationJobRow } from '@/api/modules/operations'
import { PaginationToolbar } from '@/components/data/PaginationToolbar'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Card } from '@/components/ui/card'
import { useServerPagination } from '@/hooks/useServerPagination'

const PAGE_SIZE = 20

export function JobsPage() {
  const pagination = useServerPagination<OperationJobRow>({
    pageSize: PAGE_SIZE,
    load: ({ page, pageSize, search }) => listOperationsJobs({ page, page_size: pageSize, search }),
  })
  const { rows: jobs, meta, loading, error } = pagination

  return (
    <ConsoleLayout
      eyebrow="Operations"
      title="Jobs control plane"
      description="集中查看后台 durable jobs 的状态、租约尝试和失败信息，为后续 webhook / SSE 分发与运营排障提供统一入口。"
    >
      <PaginationToolbar
        page={meta.page}
        totalPages={meta.total_pages}
        total={meta.total}
        searchInput={pagination.searchInput}
        appliedSearch={pagination.appliedSearch}
        loading={loading}
        searchLabel="搜索任务"
        onSearchInput={pagination.setSearchInput}
        onSearch={() => pagination.submitSearch()}
        onClearSearch={pagination.clearSearch}
        onPageChange={pagination.goToPage}
      />
      {error ? (
        <Card className="flex flex-wrap items-center gap-3 p-4 text-sm text-destructive" role="alert">
          <span>Failed to load operations jobs.</span>
          <button type="button" className="underline" onClick={() => pagination.retry()}>重试</button>
        </Card>
      ) : null}
      <div className="overflow-hidden rounded-2xl border border-border bg-card">
        <table className="min-w-full divide-y divide-border text-sm">
          <thead className="bg-muted/40 text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Kind</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Tenant</th>
              <th className="px-4 py-3 font-medium">Attempts</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {jobs.map((job) => (
              <tr key={job.id}>
                <td className="px-4 py-3">{job.kind}</td>
                <td className="px-4 py-3">{job.status}</td>
                <td className="px-4 py-3">{job.tenantId ?? job.tenant_id ?? '-'}</td>
                <td className="px-4 py-3">{job.attemptCount ?? job.attempt_count ?? 0}</td>
              </tr>
            ))}
            {!loading && jobs.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-muted-foreground" colSpan={4}>
                  No operations jobs yet
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </ConsoleLayout>
  )
}
