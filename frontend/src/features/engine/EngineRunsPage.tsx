import { FormEvent, useEffect, useState } from 'react'

import {
  listEngineDeployments,
  listEngineRuns,
  listEngineSourceBuilds,
  submitEngineSourceBuild,
  type EngineDeploymentRow,
  type EngineRunRow,
  type EngineSourceBuildAutonomousBuild,
  type EngineSourceBuildRow,
} from '@/api/modules/engine'
import { RunTimeline } from '@/components/diagnostics/RunTimeline'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

function getSourceId(row: EngineSourceBuildRow) {
  return row.sourceId ?? row.source_id ?? row.payload.canonical_url ?? row.id
}

function getAutonomousBuild(row: EngineSourceBuildRow): EngineSourceBuildAutonomousBuild | undefined {
  return row.payload.autonomous_build
}

function getSourceRuleName(row: EngineSourceBuildRow) {
  const sourceRule = row.payload.source_rule
  if (sourceRule && typeof sourceRule === 'object' && 'bookSourceName' in sourceRule) {
    const name = sourceRule.bookSourceName
    if (typeof name === 'string' && name.trim()) {
      return name
    }
  }
  return row.payload.keyword || getSourceId(row)
}

function getValidationSummary(autonomousBuild: EngineSourceBuildAutonomousBuild | undefined) {
  const validation = autonomousBuild?.validation
  if (!validation) return 'validation - / -'
  return `validation ${validation.grade ?? '-'} / ${validation.quality_score ?? '-'}`
}

function getProbeSummary(autonomousBuild: EngineSourceBuildAutonomousBuild | undefined) {
  const probe = autonomousBuild?.probe
  if (!probe) return 'search/toc/content - / - / -'
  return `search/toc/content ${probe.search_status ?? '-'} / ${probe.toc_status ?? '-'} / ${probe.content_status ?? '-'}`
}

export function EngineRunsPage() {
  const [runs, setRuns] = useState<EngineRunRow[]>([])
  const [deployments, setDeployments] = useState<EngineDeploymentRow[]>([])
  const [sourceBuilds, setSourceBuilds] = useState<EngineSourceBuildRow[]>([])
  const [sourceUrl, setSourceUrl] = useState('')
  const [keyword, setKeyword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true

    async function load() {
      const [runsResponse, deploymentsResponse, sourceBuildsResponse] = await Promise.all([
        listEngineRuns(),
        listEngineDeployments(),
        listEngineSourceBuilds(),
      ])
      if (!mounted) return
      setRuns(runsResponse.data)
      setDeployments(deploymentsResponse.data)
      setSourceBuilds(sourceBuildsResponse.data)
    }

    void load().catch(() => {
      if (mounted) {
        setError('Failed to load engine diagnostics')
      }
    })
    return () => {
      mounted = false
    }
  }, [])

  async function refreshSourceBuilds() {
    const sourceBuildsResponse = await listEngineSourceBuilds()
    setSourceBuilds(sourceBuildsResponse.data)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setFeedback(null)
    setError(null)
    try {
      const response = await submitEngineSourceBuild({
        url: sourceUrl,
        keyword,
      })
      setFeedback(`Queued job ${response.data.job_id}`)
      await refreshSourceBuilds()
      setSourceUrl('')
      setKeyword('')
    } catch {
      setError('Failed to queue source build')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <ConsoleLayout
      eyebrow="Engine"
      title="Rule engine console"
      description="把规则写源入口、候选规则验证和部署诊断放在同一页，给 console 操作员直接提交 URL、观察 probe 结果并追踪 deployment decision。"
    >
      <div className="grid gap-5 xl:grid-cols-[minmax(360px,0.8fr)_minmax(0,1.2fr)]">
        <section className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
          <div className="border-b border-border bg-muted/30 px-5 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-primary">Rule lab</p>
            <h2 className="mt-2 text-xl font-semibold text-foreground">Rule writing studio</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              输入站点入口后端会排队执行 source.build，产出 source_rule、rule_patch 和 live probe 验证摘要。
            </p>
          </div>
          <form className="space-y-4 p-5" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground" htmlFor="engine-source-url">
                Source URL
              </label>
              <Input
                id="engine-source-url"
                name="source-url"
                placeholder="https://example.test/books/"
                value={sourceUrl}
                onChange={(event) => setSourceUrl(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground" htmlFor="engine-source-keyword">
                Keyword
              </label>
              <Input
                id="engine-source-keyword"
                name="keyword"
                placeholder="sample"
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
              />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={submitting}>
                Start source build
              </Button>
              {feedback ? <span className="text-sm font-medium text-emerald-600 dark:text-emerald-400">{feedback}</span> : null}
              {error ? <span className="text-sm font-medium text-rose-600 dark:text-rose-400">{error}</span> : null}
            </div>
          </form>
        </section>

        <section className="rounded-2xl border border-border bg-card p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                Candidate source versions
              </p>
              <h2 className="mt-2 text-xl font-semibold text-foreground">Live rule candidates</h2>
            </div>
            <Badge variant="outline" className="px-3 py-1">
              {sourceBuilds.length} candidates
            </Badge>
          </div>

          <div className="mt-5 grid gap-3">
            {sourceBuilds.map((row) => {
              const autonomousBuild = getAutonomousBuild(row)
              const probe = autonomousBuild?.probe
              return (
                <article key={row.id} className="rounded-xl border border-border bg-background/60 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-foreground">{getSourceId(row)}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {getSourceRuleName(row)} · {row.id}
                      </p>
                    </div>
                    <Badge variant={row.status === 'candidate' ? 'warning' : 'secondary'}>{row.status}</Badge>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    <div className="rounded-lg border border-border bg-muted/30 p-3">
                      <p className="text-xs font-medium text-muted-foreground">automation</p>
                      <p className="mt-2 text-sm font-semibold text-foreground">
                        {autonomousBuild?.decision ?? '-'}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">{autonomousBuild?.strategy ?? '-'}</p>
                    </div>
                    <div className="rounded-lg border border-border bg-muted/30 p-3">
                      <p className="text-xs font-medium text-muted-foreground">validation</p>
                      <p className="mt-2 text-sm font-semibold text-foreground">
                        {getValidationSummary(autonomousBuild)}
                      </p>
                    </div>
                    <div className="rounded-lg border border-border bg-muted/30 p-3">
                      <p className="text-xs font-medium text-muted-foreground">probe</p>
                      <p className="mt-2 text-sm font-semibold text-foreground">{getProbeSummary(autonomousBuild)}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {probe?.sample_title ?? probe?.failure_reason ?? '-'}
                      </p>
                    </div>
                  </div>
                </article>
              )
            })}
            {sourceBuilds.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border p-6 text-sm text-muted-foreground">
                No console source build candidates yet
              </div>
            ) : null}
          </div>
        </section>
      </div>

      <section className="space-y-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">
            Diagnostics timeline
          </p>
          <h2 className="mt-2 text-xl font-semibold text-foreground">Engine runs and deployment decisions</h2>
        </div>
        <RunTimeline runs={runs} deployments={deployments} />
      </section>
    </ConsoleLayout>
  )
}
