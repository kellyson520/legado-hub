import { Link } from 'react-router-dom'

import { settingsPath } from './settingsRegistry'

const STEPS = [
  ['1', 'Extract', 'Read canonical chapters and emit cited candidates.'],
  ['2', 'Verify', 'Independently test claims against immutable evidence spans.'],
  ['3', 'Adjudicate', 'Resolve disagreements and retain the decision trail.'],
  ['4', 'Audit', 'Re-check only the affected facts when new chapters arrive.'],
]

export function AgentOverviewSettings() {
  return (
    <section className="rounded-md border border-border bg-card p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Evidence-first pipeline</p>
      <h2 className="mt-2 text-xl font-semibold text-foreground">Analysis that can show its work</h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">Source search and reading remain independent. The Agent receives citation-bounded tools, persists claims separately from raw context, and lets independent roles challenge a conclusion.</p>
      <ol className="mt-6 grid gap-3 md:grid-cols-2">{STEPS.map(([number, title, description]) => <li key={number} className="rounded-md border border-border bg-muted/30 p-4"><span className="text-xs font-semibold text-primary">{number}</span><h3 className="mt-1 text-sm font-semibold text-foreground">{title}</h3><p className="mt-1 text-sm leading-5 text-muted-foreground">{description}</p></li>)}</ol>
      <div className="mt-5 flex flex-wrap gap-3 text-sm"><Link className="font-medium text-primary underline-offset-4 hover:underline" to={settingsPath('agents', 'roles')}>Configure role routes</Link><Link className="font-medium text-primary underline-offset-4 hover:underline" to={settingsPath('agents', 'governance')}>Set evidence policy</Link></div>
    </section>
  )
}
