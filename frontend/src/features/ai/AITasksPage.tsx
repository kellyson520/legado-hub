import { listAITasks, type AITaskRow } from '@/api/modules/ai'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { useServerPagination } from '@/hooks/useServerPagination'

export function AITasksPage() {
  const pagination = useServerPagination<AITaskRow>({
    pageSize: 20,
    load: ({ page, pageSize, search }) => listAITasks({ page, page_size: pageSize, search }),
  })
  const { rows: tasks } = pagination

  return (
    <ConsoleLayout
      eyebrow="AI"
      title="Inference workbench"
      description="这里收敛结构化分析任务，持续暴露 provider、model、成本与状态，方便后续接入真实 provider 平台。"
    >
      <PaginatedListControls
        pagination={pagination}
        empty={!pagination.loading && tasks.length === 0}
        loadingLabel="正在加载 AI 任务…"
        errorLabel="Failed to load AI tasks."
        emptyLabel="暂无 AI 任务。"
        searchLabel="搜索 AI 任务"
      />
      <div className="space-y-4">
        <div className="grid grid-cols-4 gap-3 rounded-md border border-border bg-muted/50 p-4 text-xs font-medium text-muted-foreground">
          <span>task</span>
          <span>status</span>
          <span>provider</span>
          <span>model</span>
        </div>
        {tasks.map((task) => (
          <article
            key={task.id}
            className="grid grid-cols-4 gap-3 rounded-md border border-border bg-card p-4 text-sm text-foreground shadow-sm"
          >
            <span>{task.name}</span>
            <span>{task.status}</span>
            <span>{task.provider}</span>
            <span>{task.model}</span>
          </article>
        ))}
      </div>
    </ConsoleLayout>
  )
}
