import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { settingsPath } from './settingsRegistry'

export function AgentAuditSettings() {
  return (
    <section className="rounded-md border border-border bg-card p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Operational evidence</p>
      <h2 className="mt-2 text-xl font-semibold text-foreground">Audit before you automate</h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">Every future dry run will produce an inspectable tool-call and decision record. Provider keys and raw credentials are intentionally unavailable from this screen.</p>
      <div className="mt-6 grid gap-3 sm:grid-cols-3"><div className="rounded-md border border-border bg-muted/30 p-4 text-sm text-muted-foreground">Dry-run execution becomes available when the resumable task runtime is enabled.</div><Link to="/operations/agent-runs" className="rounded-md border border-border bg-muted/30 p-4 text-sm font-medium text-primary underline-offset-4 hover:underline">Open decision logs</Link><Link to={settingsPath('agents', 'automation')} className="rounded-md border border-border bg-muted/30 p-4 text-sm font-medium text-primary underline-offset-4 hover:underline">Open emergency pause</Link></div>
      <div className="mt-5"><Button type="button" variant="outline" disabled title="Available with the resumable task runtime">Run dry audit</Button></div>
    </section>
  )
}
