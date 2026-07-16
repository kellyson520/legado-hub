import { listNovelTasks, type NovelTaskRow } from '@/api/modules/novel'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { useServerPagination } from '@/hooks/useServerPagination'
import { toPaginatedQueryParams } from '@/lib/pagination'

export function NovelTasksPage() {
  const pagination = useServerPagination<NovelTaskRow>({
    pageSize: 20,
    load: (request) => listNovelTasks(toPaginatedQueryParams(request)),
  })
  const { rows: tasks } = pagination

  return (
    <ConsoleLayout
      eyebrow="Novel"
      title="Narrative processing queue"
      description="小说侧任务以 ingestion / processing / result 的工作流形态呈现，作为后续 provider 平台接入的操作入口。"
    >
      <PaginatedListControls
        pagination={pagination}
        empty={!pagination.loading && tasks.length === 0}
        loadingLabel="正在加载小说…"
        errorLabel="Failed to load novels."
        emptyLabel="暂无小说任务。"
        searchLabel="搜索小说"
      />
      <div className="space-y-3">
        {tasks.map((task) => (
          <article key={task.id} className="rounded-md border border-border bg-card p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-foreground">{task.title}</h3>
            <p className="mt-3 text-sm text-muted-foreground">
              {task.pipeline} · {task.provider} · {task.status}
            </p>
          </article>
        ))}
      </div>
    </ConsoleLayout>
  )
}
