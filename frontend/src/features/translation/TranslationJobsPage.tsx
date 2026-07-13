import { useEffect, useState } from 'react'

import { listTranslationJobs, type TranslationJobRow } from '@/api/modules/translation'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'

export function TranslationJobsPage() {
  const [jobs, setJobs] = useState<TranslationJobRow[]>([])

  useEffect(() => {
    let mounted = true

    async function load() {
      const response = await listTranslationJobs()
      if (!mounted) return
      setJobs(response.data)
    }

    load()
    return () => {
      mounted = false
    }
  }, [])

  return (
    <ConsoleLayout
      eyebrow="Translation"
      title="Chunk orchestration board"
      description="翻译任务按 provider、目标语言与进度统一展示，后续这里继续扩展 chunk 级重试、词典与质量状态。"
    >
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
