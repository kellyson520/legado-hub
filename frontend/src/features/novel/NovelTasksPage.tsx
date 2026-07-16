import { listNovelTasks, type NovelTaskRow } from '@/api/modules/novel'
import { PaginationToolbar } from '@/components/data/PaginationToolbar'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Card } from '@/components/ui/card'
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
      {error ? <Card className="flex items-center gap-3 p-4 text-sm text-destructive" role="alert"><span>Failed to load novels.</span><button type="button" className="underline" onClick={() => pagination.retry()}>重试</button></Card> : null}
      <div className="space-y-3">
        {tasks.map((task) => (
          <article key={task.id} className="rounded-md border border-border bg-card p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-foreground">{task.title}</h3>
            <p className="mt-3 text-sm text-muted-foreground">
              {task.pipeline} · {task.provider} · {task.status}
            </p>
          </article>
        ))}
        {!loading && tasks.length === 0 ? <Card className="p-5 text-sm text-muted-foreground">暂无小说任务。</Card> : null}
      </div>
    </ConsoleLayout>
  )
}
