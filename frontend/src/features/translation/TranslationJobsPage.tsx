import { listTranslationJobs, type TranslationJobRow } from '@/api/modules/translation'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { useServerPagination } from '@/hooks/useServerPagination'

export function TranslationJobsPage() {
  const pagination = useServerPagination<TranslationJobRow>({
    pageSize: 20,
    load: listTranslationJobs,
  })
  const { rows: jobs } = pagination

  return (
    <ConsoleLayout
      eyebrow="Translation"
      title="Chunk orchestration board"
      description="翻译任务按 provider、目标语言与进度统一展示，后续这里继续扩展 chunk 级重试、词典与质量状态。"
    >
      <PaginatedListControls
        pagination={pagination}
        empty={!pagination.loading && jobs.length === 0}
        loadingLabel="正在加载翻译任务…"
        errorLabel="Failed to load translation jobs."
        emptyLabel="暂无翻译任务。"
        searchLabel="搜索翻译任务"
      />
      <div className="space-y-3">
        {jobs.map((job) => (
          <article key={job.id} className="rounded-md border border-border bg-card p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-foreground">{job.name}</h3>
            <p className="mt-3 text-sm text-muted-foreground">
              {job.provider} · {job.targetLanguage} · {job.progress}
            </p>
          </article>
        ))}
      </div>
    </ConsoleLayout>
  )
}
