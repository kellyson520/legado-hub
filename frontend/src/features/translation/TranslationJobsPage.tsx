import { listTranslationJobs, type TranslationJobRow } from '@/api/modules/translation'
import { PaginationToolbar } from '@/components/data/PaginationToolbar'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Card } from '@/components/ui/card'
import { useServerPagination } from '@/hooks/useServerPagination'

export function TranslationJobsPage() {
  const pagination = useServerPagination<TranslationJobRow>({
    pageSize: 20,
    load: ({ page, pageSize, search }) => listTranslationJobs({ page, page_size: pageSize, search }),
  })
  const { rows: jobs, meta, loading, error } = pagination

  return (
    <ConsoleLayout
      eyebrow="Translation"
      title="Chunk orchestration board"
      description="翻译任务按 provider、目标语言与进度统一展示，后续这里继续扩展 chunk 级重试、词典与质量状态。"
    >
      <PaginationToolbar
        page={meta.page}
        totalPages={meta.total_pages}
        total={meta.total}
        searchInput={pagination.searchInput}
        appliedSearch={pagination.appliedSearch}
        loading={loading}
        searchLabel="搜索翻译任务"
        onSearchInput={pagination.setSearchInput}
        onSearch={() => pagination.submitSearch()}
        onClearSearch={pagination.clearSearch}
        onPageChange={pagination.goToPage}
      />
      {error ? <Card className="flex items-center gap-3 p-4 text-sm text-destructive" role="alert"><span>Failed to load translation jobs.</span><button type="button" className="underline" onClick={() => pagination.retry()}>重试</button></Card> : null}
      <div className="space-y-3">
        {jobs.map((job) => (
          <article key={job.id} className="rounded-md border border-border bg-card p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-foreground">{job.name}</h3>
            <p className="mt-3 text-sm text-muted-foreground">
              {job.provider} · {job.targetLanguage} · {job.progress}
            </p>
          </article>
        ))}
        {!loading && jobs.length === 0 ? <Card className="p-5 text-sm text-muted-foreground">暂无翻译任务。</Card> : null}
      </div>
    </ConsoleLayout>
  )
}
