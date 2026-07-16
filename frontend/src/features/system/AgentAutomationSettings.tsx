import { Button } from '@/components/ui/button'
import { StatusMessage } from '@/components/data/StatusMessage'
import { SettingsEffectiveStatus } from './SettingsEffectiveStatus'
import { useAgentSettingsSection } from './useAgentSettingsSection'

type AutomationSettings = { enabled: boolean; background_incremental_enabled: boolean; emergency_pause: boolean }

const DEFAULTS: AutomationSettings = { enabled: true, background_incremental_enabled: false, emergency_pause: false }

const FIELDS: Array<{ key: keyof AutomationSettings; label: string; description: string }> = [
  { key: 'enabled', label: 'Enable analysis Agents', description: 'Allows manually started evidence-analysis tasks.' },
  { key: 'background_incremental_enabled', label: 'Run incremental analysis in background', description: 'Only new, ingested chapters are queued.' },
  { key: 'emergency_pause', label: 'Emergency pause', description: 'Stops new Agent task execution without deleting evidence or drafts.' },
]

export function AgentAutomationSettings() {
  const section = useAgentSettingsSection('automation', DEFAULTS)
  return (
    <section className="rounded-md border border-border bg-card p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Queue control</p>
      <h2 className="mt-2 text-xl font-semibold text-foreground">Deliberate automation, reversible controls</h2>
      <div className="mt-6 space-y-3">
        {FIELDS.map((field) => <label key={field.key} className="flex items-start justify-between gap-4 rounded-md border border-border bg-muted/30 p-4"><span><strong className="block text-sm text-foreground">{field.label}</strong><span className="mt-1 block text-sm text-muted-foreground">{field.description}</span></span><input aria-label={field.label} type="checkbox" className="mt-1 h-4 w-4" checked={section.value[field.key]} onChange={(event) => section.patch({ [field.key]: event.target.checked } as Partial<AutomationSettings>)} /></label>)}
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-3"><Button type="button" disabled={section.loading || section.saving} onClick={() => void section.save()}>{section.saving ? 'Saving…' : 'Save automation settings'}</Button><SettingsEffectiveStatus updatedAt={section.updatedAt} /></div>
      <StatusMessage tone="error" message={section.error} className="mt-3" />
    </section>
  )
}
