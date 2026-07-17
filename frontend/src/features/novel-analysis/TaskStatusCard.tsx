import type { AnalysisTask } from '@/api/modules/novelAnalysis'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { Button } from '@/components/ui/button'
import { statusText } from '@/lib/i18n'

interface TaskStatusCardProps {
  task: AnalysisTask
  onRun: (taskId: string) => void
  onPause: (taskId: string) => void
  onResume: (taskId: string) => void
}

export function TaskStatusCard({ task, onRun, onPause, onResume }: TaskStatusCardProps) {
  const { locale, t } = useLanguage()
  const selectedCount = task.checkpoint.selected_evidence_ids?.length ?? 0
  const maxTools = task.policy.max_tool_calls_per_task ?? 0
  const canPause = task.status === 'queued' || task.status === 'running'
  const canResume = task.status === 'paused'

  return <article className="rounded-md border border-border/80 bg-background/50 p-3">
    <div className="flex items-center justify-between gap-3">
      <p className="font-mono text-xs text-muted-foreground">{task.id}</p>
      <span className="rounded-full border border-border px-2 py-0.5 text-xs font-medium">{statusText(task.status, locale)}</span>
    </div>
    <p className="mt-2 text-xs text-muted-foreground">{t('analysis.evidence', { count: selectedCount })} · {t('analysis.tools', { used: task.tool_call_count, max: maxTools || '—' })}</p>
    {task.checkpoint.blocked_reason ? <p className="mt-2 text-xs text-destructive">{task.checkpoint.blocked_reason}</p> : null}
    {task.checkpoint.outcomes?.map((outcome) => <p key={outcome.claim_id} className="mt-2 text-xs text-muted-foreground">{outcome.claim_id}: {outcome.reasons.join('; ') || outcome.verdict}</p>)}
    <div className="mt-3 flex gap-2">
      {task.status === 'queued' ? <Button size="sm" aria-label={`${t('analysis.runTask', { id: task.id })}`} onClick={() => onRun(task.id)}>{t('analysis.runNow')}</Button> : null}
      {canPause ? <Button size="sm" variant="outline" aria-label={`${t('analysis.pauseTask', { id: task.id })}`} onClick={() => onPause(task.id)}>{t('analysis.pause')}</Button> : null}
      {canResume ? <Button size="sm" aria-label={`${t('analysis.resumeTask', { id: task.id })}`} onClick={() => onResume(task.id)}>{t('analysis.resume')}</Button> : null}
    </div>
  </article>
}
