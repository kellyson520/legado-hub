import { listAuditLogs, type AuditLogRow } from '@/api/modules/admin'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { DataTable, type DataTableColumn } from '@/components/data/DataTable'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { useServerPagination } from '@/hooks/useServerPagination'

export function AdminAuditPage() {
  const { t } = useLanguage()
  const pagination = useServerPagination<AuditLogRow>({
    pageSize: 50,
    load: listAuditLogs,
  })
  const { rows: logs } = pagination
  const columns: DataTableColumn<AuditLogRow>[] = [
    { id: 'action', header: t('Action'), cell: (log) => <span className="font-medium text-foreground">{log.action}</span> },
    { id: 'resource', header: t('Resource'), cell: (log) => log.resource },
    { id: 'detail', header: t('Details'), cell: (log) => <span className="text-muted-foreground">{log.detail}</span> },
    { id: 'created', header: t('Created'), cell: (log) => log.createdAt ?? '-' },
  ]

  return (
    <ConsolePageShell
      eyebrow="Audit"
      title="Operational trace ledger"
      description="把高风险操作与自动化动作都纳入统一审计视图，便于排查部署、回滚、授权与任务执行链路。"
    >
      <PaginatedListControls
        pagination={pagination}
        empty={false}
        loadingLabel="正在加载审计记录…"
        errorLabel="Failed to load audit rows."
        emptyLabel="No audit rows loaded yet."
        searchLabel="搜索审计"
      />
      <DataTable rows={logs} columns={columns} getRowKey={(log) => log.id} emptyLabel={t('No audit rows loaded yet.')} />
    </ConsolePageShell>
  )
}
