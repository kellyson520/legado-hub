import { listTranslationJobs, type TranslationJobRow } from '@/api/modules/translation'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { DataTable, type DataTableColumn } from '@/components/data/DataTable'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { StatusBadge } from '@/components/data/StatusBadge'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { useServerPagination } from '@/hooks/useServerPagination'

export function TranslationJobsPage() {
  const { t } = useLanguage()
  const pagination = useServerPagination<TranslationJobRow>({
    pageSize: 20,
    load: listTranslationJobs,
  })
  const { rows: jobs } = pagination
  const columns: DataTableColumn<TranslationJobRow>[] = [
    { id: 'name', header: t('Name'), cell: (job) => <span className="font-medium text-foreground">{job.name}</span> },
    { id: 'status', header: t('Status'), cell: (job) => <StatusBadge status={job.status} /> },
    { id: 'provider', header: t('provider'), cell: (job) => job.provider },
    { id: 'target', header: t('Target language'), cell: (job) => job.targetLanguage },
    { id: 'progress', header: t('Progress'), cell: (job) => job.progress },
  ]

  return (
    <ConsolePageShell
      eyebrow="Translation"
      title="Chunk orchestration board"
      description="翻译任务按 provider、目标语言与进度统一展示，后续这里继续扩展 chunk 级重试、词典与质量状态。"
    >
      <PaginatedListControls
        pagination={pagination}
        empty={false}
        loadingLabel="正在加载翻译任务…"
        errorLabel="Failed to load translation jobs."
        emptyLabel="暂无翻译任务。"
        searchLabel="搜索翻译任务"
      />
      <DataTable rows={jobs} columns={columns} getRowKey={(job) => job.id} emptyLabel={t('暂无翻译任务。')} />
    </ConsolePageShell>
  )
}
