import { Badge } from '@/components/ui/badge'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { statusText } from '@/lib/i18n'

import type { EngineDeploymentRow, EngineRunRow } from '@/api/modules/engine'

function getSourceVersionId(item: EngineDeploymentRow | EngineRunRow) {
  return item.sourceVersionId ?? item.source_version_id
}

function getStepResults(run: EngineRunRow) {
  const raw = run.stepResults ?? run.step_results ?? {}
  return Object.fromEntries(
    Object.entries(raw).map(([step, detail]) => [
      step,
      {
        passed: Boolean(detail.passed),
        elapsedMs: detail.elapsedMs ?? detail.elapsed_ms ?? 0,
      },
    ])
  )
}

export function RunTimeline({
  runs,
  deployments,
}: {
  runs: EngineRunRow[]
  deployments: EngineDeploymentRow[]
}) {
  const { locale, t } = useLanguage()
  return (
    <div className="space-y-4">
      {runs.map((run) => {
        const sourceVersionId = getSourceVersionId(run)
        const deployment = deployments.find((item) => getSourceVersionId(item) === sourceVersionId)
        const stepResults = getStepResults(run)
        return (
          <article
            key={run.id}
            className="rounded-md border border-border bg-card p-5 shadow-sm"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-medium text-muted-foreground">{t('analysis.runId')}</p>
                <h3 className="mt-2 text-lg font-semibold text-foreground">{run.id}</h3>
              </div>
              <Badge variant="success" className="border-none bg-emerald-100 px-3 py-1 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                {t('analysis.grade', { grade: run.grade })}
              </Badge>
            </div>

            <div className="mt-6 grid gap-3 md:grid-cols-3">
              {Object.entries(stepResults).map(([step, detail]) => (
                <div key={step} className="rounded-md border border-border bg-muted/35 p-4">
                  <p className="text-sm font-medium lowercase text-foreground">{step}</p>
                  <p className="mt-2 text-xs text-muted-foreground">{detail.elapsedMs} ms</p>
                  <p className={`mt-3 text-sm ${detail.passed ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                    {detail.passed ? t('analysis.passed') : t('analysis.failed')}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-6 rounded-md border border-primary/25 bg-accent/60 p-4">
              <p className="text-xs font-semibold text-primary">{t('analysis.deploymentDecision')}</p>
              <p className="mt-3 text-sm text-foreground">
                {deployment ? `${deployment.action} -> ${statusText(deployment.status, locale)}` : t('analysis.waitingDeploymentReview')}
              </p>
            </div>
          </article>
        )
      })}
    </div>
  )
}
