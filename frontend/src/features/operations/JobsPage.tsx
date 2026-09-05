import { listOperationsJobs, type OperationJobRow } from '@/api/modules/operations'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { DataTable, type DataTableColumn } from '@/components/data/DataTable'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { StatusBadge } from '@/components/data/StatusBadge'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { useServerPagination } from '@/hooks/useServerPagination'

const PAGE_SIZE = 20

export function JobsPage() {
  const { t } = useLanguage()
  const pagination = useServerPagination<OperationJobRow>({
    pageSize: PAGE_SIZE,
    load: listOperationsJobs,
  })
  const { rows: jobs } = pagination
  const columns: DataTableColumn<OperationJobRow>[] = [
    { id: 'kind', header: t('Kind'), cell: (job) => job.kind },
    { id: 'status', header: t('Status'), cell: (job) => <StatusBadge status={job.status} /> },
    { id: 'tenant', header: t('Tenant'), cell: (job) => job.tenantId ?? job.tenant_id ?? '-' },
    { id: 'attempts', header: t('Attempts'), cell: (job) => job.attemptCount ?? job.attempt_count ?? 0 },
  ]

  return (
    <ConsolePageShell
      eyebrow="Operations"
      title="Jobs control plane"
      description="集中查看后台 durable jobs 的状态、租约尝试和失败信息，为后续 webhook / SSE 分发与运营排障提供统一入口。"
    >
      <PaginatedListControls
        pagination={pagination}
        empty={false}
        loadingLabel="正在加载后台任务…"
        errorLabel="Failed to load operations jobs."
        emptyLabel="No operations jobs yet"
        searchLabel="搜索任务"
      />
      <DataTable rows={jobs} columns={columns} getRowKey={(job) => job.id} emptyLabel={t('No operations jobs yet')} />
    </ConsolePageShell>
  )
}
