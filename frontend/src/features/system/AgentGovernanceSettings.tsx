import { Button } from '@/components/ui/button'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { StatusMessage } from '@/components/data/StatusMessage'
import { FormActions } from '@/components/form/FormActions'
import { FormField } from '@/components/form/FormField'
import { LocalizedContent } from '@/components/layout/LocalizedContent'
import { Input } from '@/components/ui/input'
import { SettingsEffectiveStatus } from './SettingsEffectiveStatus'
import { useAgentSettingsSection } from './useAgentSettingsSection'

type GovernanceSettings = {
  automatic_publish_explicit: boolean
  automatic_publish_inferred: boolean
  minimum_inferred_evidence: number
  require_human_review_for_identity: boolean
  require_human_review_for_conflicts: boolean
}

const DEFAULTS: GovernanceSettings = {
  automatic_publish_explicit: true,
  automatic_publish_inferred: false,
  minimum_inferred_evidence: 2,
  require_human_review_for_identity: true,
  require_human_review_for_conflicts: true,
}

export function AgentGovernanceSettings() {
  const { t } = useLanguage()
  const section = useAgentSettingsSection('governance', DEFAULTS)

  return (
    <LocalizedContent>
    <section className="rounded-md border border-border bg-card p-5 shadow-sm">
      <div className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Evidence policy</p>
        <h2 className="mt-2 text-xl font-semibold text-foreground">Publish only what the text can support</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Explicit facts can follow verified evidence. Inferred identities and conflicts stay reviewable until the evidence threshold is met.
        </p>
      </div>
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <FormField label={t('Publish explicit facts automatically')} htmlFor="agent-publish-explicit" help={t('Only after source evidence verifies the claim.')} className="flex items-start gap-3 rounded-md border border-border bg-muted/30 p-4 text-sm text-foreground">
          <input id="agent-publish-explicit" type="checkbox" checked={section.value.automatic_publish_explicit} onChange={(event) => section.patch({ automatic_publish_explicit: event.target.checked })} />
        </FormField>
        <FormField label={t('Publish inferred facts automatically')} htmlFor="agent-publish-inferred" help={t('Keep this off for a review-first workflow.')} className="flex items-start gap-3 rounded-md border border-border bg-muted/30 p-4 text-sm text-foreground">
          <input id="agent-publish-inferred" type="checkbox" checked={section.value.automatic_publish_inferred} onChange={(event) => section.patch({ automatic_publish_inferred: event.target.checked })} />
        </FormField>
        <FormField label={t('Minimum evidence spans for inferred facts')} htmlFor="agent-minimum-evidence" className="rounded-md border border-border bg-muted/30 p-4">
          <Input id="agent-minimum-evidence" type="number" min={2} max={8} value={section.value.minimum_inferred_evidence} onChange={(event) => section.patch({ minimum_inferred_evidence: Number(event.target.value) })} />
        </FormField>
        <div className="space-y-3 rounded-md border border-border bg-muted/30 p-4 text-sm text-foreground">
          <FormField label={t('Require review for identity resolution')} htmlFor="agent-review-identity"><input id="agent-review-identity" type="checkbox" checked={section.value.require_human_review_for_identity} onChange={(event) => section.patch({ require_human_review_for_identity: event.target.checked })} /></FormField>
          <FormField label={t('Require review when sources conflict')} htmlFor="agent-review-conflicts"><input id="agent-review-conflicts" type="checkbox" checked={section.value.require_human_review_for_conflicts} onChange={(event) => section.patch({ require_human_review_for_conflicts: event.target.checked })} /></FormField>
        </div>
      </div>
      <FormActions className="mt-5 justify-start">
        <Button type="button" disabled={section.loading || section.saving} onClick={() => void section.save()}>{section.saving ? 'Saving…' : 'Save governance settings'}</Button>
        <SettingsEffectiveStatus updatedAt={section.updatedAt} />
      </FormActions>
      <StatusMessage tone="error" message={section.error} className="mt-3" />
    </section>
    </LocalizedContent>
  )
}
