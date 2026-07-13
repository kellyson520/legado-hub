import { useEffect, useState } from 'react'

import { listNovelTasks, type NovelTaskRow } from '@/api/modules/novel'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'

export function NovelTasksPage() {
  const [tasks, setTasks] = useState<NovelTaskRow[]>([])

  useEffect(() => {
    let mounted = true

    async function load() {
      const response = await listNovelTasks()
      if (!mounted) return
      setTasks(response.data)
    }

    load()
    return () => {
      mounted = false
    }
  }, [])

  return (
    <ConsoleLayout
      eyebrow="Novel"
      title="Narrative processing queue"
      description="小说侧任务以 ingestion / processing / result 的工作流形态呈现，作为后续 provider 平台接入的操作入口。"
    >
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
