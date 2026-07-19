import { listAITasks, type AITaskRow } from '@/api/modules/ai'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { DataTable, type DataTableColumn } from '@/components/data/DataTable'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { StatusBadge } from '@/components/data/StatusBadge'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { useServerPagination } from '@/hooks/useServerPagination'

export function AITasksPage() {
  const { t } = useLanguage()
  const pagination = useServerPagination<AITaskRow>({
    pageSize: 20,
    load: listAITasks,
  })
  const { rows: tasks } = pagination
  const columns: DataTableColumn<AITaskRow>[] = [
    { id: 'task', header: t('task'), cell: (task) => <span className="font-medium text-foreground">{task.name}</span> },
    { id: 'status', header: t('status'), cell: (task) => <StatusBadge status={task.status} /> },
    { id: 'provider', header: t('provider'), cell: (task) => task.provider },
    { id: 'model', header: t('model'), cell: (task) => task.model },
    { id: 'cost', header: t('Cost'), cell: (task) => task.cost },
  ]

  return (
    <ConsolePageShell
      eyebrow="AI"
      title="Inference workbench"
      description="这里收敛结构化分析任务，持续暴露 provider、model、成本与状态，方便后续接入真实 provider 平台。"
    >
      <PaginatedListControls
        pagination={pagination}
        empty={false}
        loadingLabel="正在加载 AI 任务…"
        errorLabel="Failed to load AI tasks."
        emptyLabel="暂无 AI 任务。"
        searchLabel="搜索 AI 任务"
      />
      <DataTable rows={tasks} columns={columns} getRowKey={(task) => task.id} emptyLabel={t('暂无 AI 任务。')} />
    </ConsolePageShell>
  )
}
