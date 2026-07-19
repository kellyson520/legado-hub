import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  getEvidence, getWorkSnapshot, getWorkTasks, pauseAnalysisTask, resumeAnalysisTask, runAnalysisTask,
  type AnalysisTask, type EvidenceCitation, type WorkSnapshot,
} from '@/api/modules/novelAnalysis'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { DetailPanel } from '@/components/detail/DetailPanel'
import { ErrorState, LoadingState } from '@/components/data/ListStates'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { Button } from '@/components/ui/button'

import { EvidenceDrawer } from './EvidenceDrawer'
import { TaskStatusCard } from './TaskStatusCard'

export function WorkAnalysisPage() {
  const { t } = useLanguage()
  const { workId = '' } = useParams()
  const [snapshot, setSnapshot] = useState<WorkSnapshot | null>(null)
  const [evidence, setEvidence] = useState<EvidenceCitation | null>(null)
  const [tasks, setTasks] = useState<AnalysisTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let current = true
    setLoading(true)
    setError(null)
    void Promise.all([getWorkSnapshot(workId), getWorkTasks(workId)])
      .then(([work, taskList]) => {
        if (!current) return
        setSnapshot(work.data)
        setTasks(taskList.data.items)
      })
      .catch(() => {
        if (current) setError(t('error.generic'))
      })
      .finally(() => {
        if (current) setLoading(false)
      })
    return () => { current = false }
  }, [t, workId])
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

  return <ConsolePageShell eyebrow="Novel analysis" title="Evidence-backed work analysis" description="人物、关系、事件与世界观结论均可回到精确正文片段。">
    {loading ? <LoadingState label={t('common.loading')} /> : error ? <ErrorState label={error} onRetry={() => window.location.reload()} retryLabel={t('common.retry')} /> : (
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="space-y-4">
          <ClaimSection title="Published claims" claims={snapshot?.published_claims ?? []} onOpenEvidence={openEvidence} />
          <ClaimSection title="Candidate claims" claims={snapshot?.candidate_claims ?? []} onOpenEvidence={openEvidence} />
          <DetailPanel title={t('Open conflicts')} items={[{ label: t('{count} awaiting adjudication', { count: snapshot?.open_conflicts.length ?? 0 }), value: snapshot?.open_conflicts.length ?? 0 }]} />
          <DetailPanel title={t('Task queue')} emptyLabel={t('No analysis task has been queued for this work.')}>
            {tasks.length ? <div className="space-y-2">{tasks.map((task) => <TaskStatusCard key={task.id} task={task} onRun={(id) => void runTask(id)} onPause={(id) => void pauseTask(id)} onResume={(id) => void resumeTask(id)} />)}</div> : null}
          </DetailPanel>
        </div>
        <EvidenceDrawer evidence={evidence} />
      </div>
    )}
  </ConsolePageShell>
}

function ClaimSection({ title, claims, onOpenEvidence, className = '' }: {
  title: string
  claims: WorkSnapshot['published_claims']
  onOpenEvidence: (evidenceId: string) => Promise<void>
  className?: string
}) {
  const { t } = useLanguage()
  return <DetailPanel title={t(title)} emptyLabel={t('None.')} className={className}>
    {claims.length ? <div className="space-y-2">{claims.map((claim) => <Button key={claim.id} variant="outline" className="h-auto w-full justify-start whitespace-normal text-left" onClick={() => void onOpenEvidence(claim.evidence_ids[0])}>{claim.subject_entity_id} · {claim.predicate}</Button>)}</div> : null}
  </DetailPanel>
}
