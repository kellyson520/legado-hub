import { listAITasks, type AITaskRow } from '@/api/modules/ai'
import { ListStatus } from '@/components/data/ListStatus'
import { PaginationToolbar } from '@/components/data/PaginationToolbar'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { useServerPagination } from '@/hooks/useServerPagination'

export function AITasksPage() {
  const pagination = useServerPagination<AITaskRow>({
    pageSize: 20,
    load: ({ page, pageSize, search }) => listAITasks({ page, page_size: pageSize, search }),
  })
  const { rows: tasks, meta, loading, error } = pagination

  return (
    <ConsoleLayout
      eyebrow="AI"
      title="Inference workbench"
      description="这里收敛结构化分析任务，持续暴露 provider、model、成本与状态，方便后续接入真实 provider 平台。"
    >
      <PaginationToolbar
        page={meta.page}
        totalPages={meta.total_pages}
        total={meta.total}
        searchInput={pagination.searchInput}
        appliedSearch={pagination.appliedSearch}
        loading={loading}
        searchLabel="搜索 AI 任务"
        onSearchInput={pagination.setSearchInput}
        onSearch={() => pagination.submitSearch()}
        onClearSearch={pagination.clearSearch}
        onPageChange={pagination.goToPage}
      />
      <ListStatus
        loading={loading}
        error={error}
        empty={!loading && tasks.length === 0}
        onRetry={pagination.retry}
        loadingLabel="正在加载 AI 任务…"
        errorLabel="Failed to load AI tasks."
        emptyLabel="暂无 AI 任务。"
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
