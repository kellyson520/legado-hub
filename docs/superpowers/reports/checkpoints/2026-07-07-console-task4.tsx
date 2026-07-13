import { useEffect, useState } from 'react'

import { listEngineDeployments, listEngineRuns, type EngineDeploymentRow, type EngineRunRow } from '@/api/modules/engine'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { RunTimeline } from '@/components/diagnostics/RunTimeline'

export function EngineRunsPage() {
  const [runs, setRuns] = useState<EngineRunRow[]>([])
  const [deployments, setDeployments] = useState<EngineDeploymentRow[]>([])

  useEffect(() => {
    let mounted = true

    async function load() {
      const [runsResponse, deploymentsResponse] = await Promise.all([listEngineRuns(), listEngineDeployments()])
      if (!mounted) return
      setRuns(runsResponse.data)
      setDeployments(deploymentsResponse.data)
    }

    load()
    return () => {
      mounted = false
    }
  }, [])

  return (
    <ConsoleLayout
      eyebrow="Engine"
      title="Diagnostics timeline"
      description="把解析运行、质量门和部署决策汇总到同一条运行时间线，给后续自动替换、回滚与修复辅助提供操作入口。"
    >
      <RunTimeline runs={runs} deployments={deployments} />
    </ConsoleLayout>
  )
}
