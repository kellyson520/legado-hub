import { listOperationsJobs, type OperationJobRow } from '@/api/modules/operations'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { useServerPagination } from '@/hooks/useServerPagination'

const PAGE_SIZE = 20

export function JobsPage() {
  const pagination = useServerPagination<OperationJobRow>({
    pageSize: PAGE_SIZE,
    load: ({ page, pageSize, search }) => listOperationsJobs({ page, page_size: pageSize, search }),
  })
  const { rows: jobs } = pagination

  return (
    <ConsoleLayout
      eyebrow="Operations"
      title="Jobs control plane"
      description="集中查看后台 durable jobs 的状态、租约尝试和失败信息，为后续 webhook / SSE 分发与运营排障提供统一入口。"
    >
      <PaginatedListControls
        pagination={pagination}
        empty={!pagination.loading && jobs.length === 0}
        loadingLabel="正在加载后台任务…"
        errorLabel="Failed to load operations jobs."
        emptyLabel="No operations jobs yet"
        searchLabel="搜索任务"
      />
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
          </tbody>
        </table>
      </div>
    </ConsoleLayout>
  )
}
