import { Button } from '@/components/ui/button'
import { SettingsEffectiveStatus } from './SettingsEffectiveStatus'
import { StatusMessage } from '@/components/data/StatusMessage'
import { useAgentSettingsSection } from './useAgentSettingsSection'
import { LocalizedContent } from '@/components/layout/LocalizedContent'

type RoleSettings = {
  extractor_route_group: string
  verifier_route_group: string
  adjudicator_route_group: string
  auditor_route_group: string
}

const DEFAULTS: RoleSettings = {
  extractor_route_group: 'novel_extract',
  verifier_route_group: 'novel_verify',
  adjudicator_route_group: 'novel_adjudicate',
  auditor_route_group: 'novel_audit',
}

const ROLE_FIELDS: Array<{ key: keyof RoleSettings; label: string; description: string }> = [
  { key: 'extractor_route_group', label: 'Extractor', description: 'Creates evidence-backed candidates from chapter spans.' },
  { key: 'verifier_route_group', label: 'Verifier', description: 'Checks every cited claim against its source span.' },
  { key: 'adjudicator_route_group', label: 'Adjudicator', description: 'Resolves independent agent disagreements.' },
  { key: 'auditor_route_group', label: 'Auditor', description: 'Runs targeted re-audits and preserves decisions.' },
]

const ROUTES = ['novel_extract', 'novel_verify', 'novel_adjudicate', 'novel_audit']

export function AgentRoleSettings() {
  const section = useAgentSettingsSection('roles', DEFAULTS)

  return (
    <LocalizedContent>
    <section className="rounded-md border border-border bg-card p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Independent roles</p>
      <h2 className="mt-2 text-xl font-semibold text-foreground">Assign models by responsibility</h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">Route groups select already-configured provider fallbacks. Credentials stay in the provider section and never appear here.</p>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {ROLE_FIELDS.map((field) => (
          <label key={field.key} className="space-y-2 rounded-md border border-border bg-muted/30 p-4">
            <span className="block text-sm font-semibold text-foreground">{field.label}</span>
            <span className="block text-sm text-muted-foreground">{field.description}</span>
            <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground" value={section.value[field.key]} onChange={(event) => section.patch({ [field.key]: event.target.value } as Partial<RoleSettings>)}>
              {ROUTES.map((route) => <option key={route} value={route}>{route}</option>)}
            </select>
          </label>
        ))}
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-3"><Button type="button" disabled={section.loading || section.saving} onClick={() => void section.save()}>{section.saving ? 'Saving…' : 'Save role settings'}</Button><SettingsEffectiveStatus updatedAt={section.updatedAt} /></div>
      <StatusMessage tone="error" message={section.error} className="mt-3" />
    </section>
    </LocalizedContent>
  )
}
