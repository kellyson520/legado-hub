import { useEffect, useState } from 'react'

import { listAITasks, type AITaskRow } from '@/api/modules/ai'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'

export function AITasksPage() {
  const [tasks, setTasks] = useState<AITaskRow[]>([])

  useEffect(() => {
    let mounted = true

    async function load() {
      const response = await listAITasks()
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
      eyebrow="AI"
      title="Inference workbench"
      description="这里收敛结构化分析任务，持续暴露 provider、model、成本与状态，方便后续接入真实 provider 平台。"
    >
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
