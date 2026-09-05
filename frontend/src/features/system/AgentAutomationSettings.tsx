import { Button } from '@/components/ui/button'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { StatusMessage } from '@/components/data/StatusMessage'
import { FormActions } from '@/components/form/FormActions'
import { FormField } from '@/components/form/FormField'
import { LocalizedContent } from '@/components/layout/LocalizedContent'
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
  const { t } = useLanguage()
  const section = useAgentSettingsSection('automation', DEFAULTS)
  return (
    <LocalizedContent>
    <section className="rounded-md border border-border bg-card p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Queue control</p>
      <h2 className="mt-2 text-xl font-semibold text-foreground">Deliberate automation, reversible controls</h2>
      <div className="mt-6 space-y-3">
        {FIELDS.map((field) => <FormField key={field.key} label={t(field.label)} htmlFor={`automation-${field.key}`} help={t(field.description)} className="flex items-start justify-between gap-4 rounded-md border border-border bg-muted/30 p-4"><input id={`automation-${field.key}`} type="checkbox" className="mt-1 h-4 w-4" checked={section.value[field.key]} onChange={(event) => section.patch({ [field.key]: event.target.checked } as Partial<AutomationSettings>)} /></FormField>)}
      </div>
      <FormActions className="mt-5 justify-start"><Button type="button" disabled={section.loading || section.saving} onClick={() => void section.save()}>{section.saving ? 'Saving…' : 'Save automation settings'}</Button><SettingsEffectiveStatus updatedAt={section.updatedAt} /></FormActions>
      <StatusMessage tone="error" message={section.error} className="mt-3" />
    </section>
    </LocalizedContent>
  )
}
