import { listNovelTasks, type NovelTaskRow } from '@/api/modules/novel'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { DataTable, type DataTableColumn } from '@/components/data/DataTable'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { StatusBadge } from '@/components/data/StatusBadge'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { useServerPagination } from '@/hooks/useServerPagination'

export function NovelTasksPage() {
  const { t } = useLanguage()
  const pagination = useServerPagination<NovelTaskRow>({
    pageSize: 20,
    load: listNovelTasks,
  })
  const { rows: tasks } = pagination
  const columns: DataTableColumn<NovelTaskRow>[] = [
    { id: 'title', header: t('Title'), cell: (task) => <span className="font-medium text-foreground">{task.title}</span> },
    { id: 'status', header: t('Status'), cell: (task) => <StatusBadge status={task.status} /> },
    { id: 'pipeline', header: t('Pipeline'), cell: (task) => task.pipeline },
    { id: 'provider', header: t('provider'), cell: (task) => task.provider },
  ]

  return (
    <ConsolePageShell
      eyebrow="Novel"
      title="Narrative processing queue"
      description="小说侧任务以 ingestion / processing / result 的工作流形态呈现，作为后续 provider 平台接入的操作入口。"
    >
      <PaginatedListControls
        pagination={pagination}
        empty={false}
        loadingLabel="正在加载小说…"
        errorLabel="Failed to load novels."
        emptyLabel="暂无小说任务。"
        searchLabel="搜索小说"
      />
      <DataTable rows={tasks} columns={columns} getRowKey={(task) => task.id} emptyLabel={t('暂无小说任务。')} />
    </ConsolePageShell>
  )
}
