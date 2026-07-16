import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  getEvidence, getWorkSnapshot, getWorkTasks, pauseAnalysisTask, resumeAnalysisTask, runAnalysisTask,
  type AnalysisTask, type EvidenceCitation, type WorkSnapshot,
} from '@/api/modules/novelAnalysis'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'

import { EvidenceDrawer } from './EvidenceDrawer'
import { TaskStatusCard } from './TaskStatusCard'

export function WorkAnalysisPage() {
  const { workId = '' } = useParams()
  const [snapshot, setSnapshot] = useState<WorkSnapshot | null>(null)
  const [evidence, setEvidence] = useState<EvidenceCitation | null>(null)
  const [tasks, setTasks] = useState<AnalysisTask[]>([])

  useEffect(() => {
    let current = true
    void Promise.all([getWorkSnapshot(workId), getWorkTasks(workId)]).then(([work, taskList]) => {
      if (!current) return
      setSnapshot(work.data)
      setTasks(taskList.data.items)
    })
    return () => { current = false }
  }, [workId])
  async function openEvidence(evidenceId: string) { setEvidence((await getEvidence(evidenceId)).data) }
  async function pauseTask(taskId: string) {
    const response = await pauseAnalysisTask(taskId)
    setTasks((current) => current.map((task) => task.id === taskId ? response.data : task))
  }
  async function resumeTask(taskId: string) {
    const response = await resumeAnalysisTask(taskId)
    setTasks((current) => current.map((task) => task.id === taskId ? response.data : task))
  }
  async function runTask(taskId: string) {
    const response = await runAnalysisTask(taskId)
    setTasks((current) => current.map((task) => task.id === taskId ? response.data : task))
  }

  return <ConsoleLayout eyebrow="Novel analysis" title="Evidence-backed work analysis" description="人物、关系、事件与世界观结论均可回到精确正文片段。">
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_21rem]">
      <section className="rounded-md border border-border bg-card p-5 shadow-sm">
        <ClaimSection title="Published claims" claims={snapshot?.published_claims ?? []} onOpenEvidence={openEvidence} />
        <ClaimSection title="Candidate claims" claims={snapshot?.candidate_claims ?? []} onOpenEvidence={openEvidence} className="mt-6" />
        <h2 className="mt-6 text-lg font-semibold">Open conflicts</h2>
        <div className="mt-2 text-sm text-muted-foreground">{snapshot?.open_conflicts.length ?? 0} awaiting adjudication</div>
        <h2 className="mt-7 text-lg font-semibold">Task queue</h2>
        <div className="mt-3 space-y-2">{tasks.length ? tasks.map((task) => <TaskStatusCard key={task.id} task={task} onRun={(id) => void runTask(id)} onPause={(id) => void pauseTask(id)} onResume={(id) => void resumeTask(id)} />) : <p className="text-sm text-muted-foreground">No analysis task has been queued for this work.</p>}</div>
      </section>
      <EvidenceDrawer evidence={evidence} />
    </div>
  </ConsoleLayout>
}

function ClaimSection({ title, claims, onOpenEvidence, className = '' }: {
  title: string
  claims: WorkSnapshot['published_claims']
  onOpenEvidence: (evidenceId: string) => Promise<void>
  className?: string
}) {
  return <section className={className}>
    <h2 className="text-lg font-semibold">{title}</h2>
    <div className="mt-3 space-y-2">
      {claims.length ? claims.map((claim) => <Button key={claim.id} variant="outline" className="h-auto w-full justify-start whitespace-normal text-left" onClick={() => void onOpenEvidence(claim.evidence_ids[0])}>{claim.subject_entity_id} · {claim.predicate}</Button>) : <p className="text-sm text-muted-foreground">None.</p>}
    </div>
  </section>
}
