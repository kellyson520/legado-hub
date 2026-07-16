import type { AnalysisTask } from '@/api/modules/novelAnalysis'
import { Button } from '@/components/ui/button'

interface TaskStatusCardProps {
  task: AnalysisTask
  onRun: (taskId: string) => void
  onPause: (taskId: string) => void
  onResume: (taskId: string) => void
}

export function TaskStatusCard({ task, onRun, onPause, onResume }: TaskStatusCardProps) {
  const selectedCount = task.checkpoint.selected_evidence_ids?.length ?? 0
  const maxTools = task.policy.max_tool_calls_per_task ?? 0
  const canPause = task.status === 'queued' || task.status === 'running'
  const canResume = task.status === 'paused'

  return <article className="rounded-md border border-border/80 bg-background/50 p-3">
    <div className="flex items-center justify-between gap-3">
      <p className="font-mono text-xs text-muted-foreground">{task.id}</p>
      <span className="rounded-full border border-border px-2 py-0.5 text-xs font-medium">{task.status}</span>
    </div>
    <p className="mt-2 text-xs text-muted-foreground">Evidence {selectedCount} · tools {task.tool_call_count}/{maxTools || '—'}</p>
    {task.checkpoint.blocked_reason ? <p className="mt-2 text-xs text-destructive">{task.checkpoint.blocked_reason}</p> : null}
    {task.checkpoint.outcomes?.map((outcome) => <p key={outcome.claim_id} className="mt-2 text-xs text-muted-foreground">{outcome.claim_id}: {outcome.reasons.join('; ') || outcome.verdict}</p>)}
    <div className="mt-3 flex gap-2">
      {task.status === 'queued' ? <Button size="sm" aria-label={`Run task ${task.id}`} onClick={() => onRun(task.id)}>Run now</Button> : null}
      {canPause ? <Button size="sm" variant="outline" aria-label={`Pause task ${task.id}`} onClick={() => onPause(task.id)}>Pause</Button> : null}
      {canResume ? <Button size="sm" aria-label={`Resume task ${task.id}`} onClick={() => onResume(task.id)}>Resume</Button> : null}
    </div>
  </article>
}
