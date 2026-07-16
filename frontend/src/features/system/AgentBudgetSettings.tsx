import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAgentSettingsSection } from './useAgentSettingsSection'

type BudgetSettings = { max_chapters_per_task: number; max_tool_calls_per_task: number; max_tokens_per_task: number; max_concurrent_tasks: number }

const DEFAULTS: BudgetSettings = { max_chapters_per_task: 12, max_tool_calls_per_task: 24, max_tokens_per_task: 24000, max_concurrent_tasks: 1 }
const FIELDS: Array<{ key: keyof BudgetSettings; label: string; min: number; max: number }> = [
  { key: 'max_chapters_per_task', label: 'Maximum chapters per task', min: 1, max: 50 },
  { key: 'max_tool_calls_per_task', label: 'Maximum tool calls per task', min: 1, max: 100 },
  { key: 'max_tokens_per_task', label: 'Maximum tokens per task', min: 1000, max: 200000 },
  { key: 'max_concurrent_tasks', label: 'Maximum concurrent tasks', min: 1, max: 8 },
]

export function AgentBudgetSettings() {
  const section = useAgentSettingsSection('budgets', DEFAULTS)
  return (
    <section className="rounded-md border border-border bg-card p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Bounded execution</p>
      <h2 className="mt-2 text-xl font-semibold text-foreground">Keep long-running analysis predictable</h2>
      <p className="mt-2 text-sm text-muted-foreground">The server applies the final safety bounds, then returns the effective values shown here.</p>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">{FIELDS.map((field) => <label key={field.key} className="space-y-2 rounded-md border border-border bg-muted/30 p-4 text-sm font-medium text-foreground" htmlFor={`budget-${field.key}`}><span>{field.label}</span><Input id={`budget-${field.key}`} type="number" min={field.min} max={field.max} value={section.value[field.key]} onChange={(event) => section.patch({ [field.key]: Number(event.target.value) } as Partial<BudgetSettings>)} /></label>)}</div>
      <div className="mt-5 flex flex-wrap items-center gap-3"><Button type="button" disabled={section.loading || section.saving} onClick={() => void section.save()}>{section.saving ? 'Saving…' : 'Save budget settings'}</Button><p role="status" className="text-sm text-muted-foreground">{section.updatedAt ? `Effective ${new Date(section.updatedAt).toLocaleString()}` : 'Effective after the first save'}</p></div>
      {section.error ? <p role="alert" className="mt-3 text-sm text-destructive">{section.error}</p> : null}
    </section>
  )
}
