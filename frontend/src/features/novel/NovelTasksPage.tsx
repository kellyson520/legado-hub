import { listNovelTasks, type NovelTaskRow } from '@/api/modules/novel'
import { ListStatus } from '@/components/data/ListStatus'
import { PaginationToolbar } from '@/components/data/PaginationToolbar'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { useServerPagination } from '@/hooks/useServerPagination'

export function NovelTasksPage() {
  const pagination = useServerPagination<NovelTaskRow>({
    pageSize: 20,
    load: ({ page, pageSize, search }) => listNovelTasks({ page, page_size: pageSize, search }),
  })
  const { rows: tasks, meta, loading, error } = pagination

  return (
    <ConsoleLayout
      eyebrow="Novel"
      title="Narrative processing queue"
      description="小说侧任务以 ingestion / processing / result 的工作流形态呈现，作为后续 provider 平台接入的操作入口。"
    >
      <PaginationToolbar
        page={meta.page}
        totalPages={meta.total_pages}
        total={meta.total}
        searchInput={pagination.searchInput}
        appliedSearch={pagination.appliedSearch}
        loading={loading}
        searchLabel="搜索小说"
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
        loadingLabel="正在加载小说…"
        errorLabel="Failed to load novels."
        emptyLabel="暂无小说任务。"
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
