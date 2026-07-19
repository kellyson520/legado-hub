import { FormEvent, useState } from 'react'

import {
  listEngineDeployments,
  listEngineRuns,
  listEngineSourceBuilds,
  submitEngineSourceBuild,
  testEngineRegex,
  type EngineDeploymentRow,
  type EngineRunRow,
  type EngineSourceBuildAutonomousBuild,
  type EngineSourceBuildRow,
  type RegexTestResult,
} from '@/api/modules/engine'
import { RunTimeline } from '@/components/diagnostics/RunTimeline'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { StatusMessage } from '@/components/data/StatusMessage'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { useServerPagination } from '@/hooks/useServerPagination'

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
  const runsPagination = useServerPagination<EngineRunRow>({
    pageSize: 20,
    load: listEngineRuns,
  })
  const deploymentsPagination = useServerPagination<EngineDeploymentRow>({
    pageSize: 20,
    load: listEngineDeployments,
  })
  const sourceBuildsPagination = useServerPagination<EngineSourceBuildRow>({
    pageSize: 20,
    load: listEngineSourceBuilds,
  })
  const { rows: runs, loading: runsLoading } = runsPagination
  const { rows: deployments, loading: deploymentsLoading } = deploymentsPagination
  const { rows: sourceBuilds, loading: sourceBuildsLoading } = sourceBuildsPagination
  const [sourceUrl, setSourceUrl] = useState('')
  const [keyword, setKeyword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [regexPattern, setRegexPattern] = useState('第(\\d+)章')
  const [regexReplacement, setRegexReplacement] = useState('章节$1')
  const [regexText, setRegexText] = useState('第12章：开始')
  const [regexResult, setRegexResult] = useState<RegexTestResult | null>(null)

  async function refreshSourceBuilds() {
    sourceBuildsPagination.reload()
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

  async function handleRegexTest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    try {
      const response = await testEngineRegex({ text: regexText, pattern: regexPattern, replacement: regexReplacement || null })
      setRegexResult(response.data)
    } catch {
      setError('正则测试请求失败。')
    }
  }

  return (
    <ConsolePageShell
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
              <StatusMessage tone="success" message={feedback} as="span" className="font-medium" />
              <StatusMessage tone="error" message={error} as="span" className="font-medium text-rose-600 dark:text-rose-400" />
            </div>
          </form>
        </section>

        <section className="rounded-2xl border border-border bg-card p-5 shadow-sm">
          <p className="text-xs font-semibold tracking-[0.24em] text-primary">规则中心</p>
          <h2 className="mt-2 text-xl font-semibold text-foreground">正则测试器</h2>
          <form className="mt-4 space-y-3" onSubmit={handleRegexTest}>
            <label className="block text-sm font-medium" htmlFor="regex-pattern">正则表达式</label>
            <Input id="regex-pattern" value={regexPattern} onChange={(event) => setRegexPattern(event.target.value)} />
            <label className="block text-sm font-medium" htmlFor="regex-replacement">替换文本（支持 $1）</label>
            <Input id="regex-replacement" value={regexReplacement} onChange={(event) => setRegexReplacement(event.target.value)} />
            <label className="block text-sm font-medium" htmlFor="regex-text">测试文本</label>
            <Textarea id="regex-text" value={regexText} onChange={(event) => setRegexText(event.target.value)} />
            <Button type="submit">测试正则</Button>
          </form>
          {regexResult ? <div className="mt-4 space-y-2 rounded-lg border border-border bg-muted/30 p-3 text-sm">{regexResult.error ? <p className="text-rose-600">语法错误：{regexResult.error}</p> : <><p>匹配数量：{regexResult.match_count}</p><p>替换预览：{regexResult.replacement_preview ?? '未设置替换文本'}</p>{regexResult.matches.map((match, index) => <p key={`${match.span.join('-')}-${index}`}>匹配：{match.match}；捕获组：{match.groups.join('、') || '无'}</p>)}</>}</div> : null}
        </section>

        <section className="rounded-2xl border border-border bg-card p-5 shadow-sm xl:col-span-2">
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

          <PaginatedListControls
            className="mt-5"
            pagination={sourceBuildsPagination}
            empty={!sourceBuildsLoading && sourceBuilds.length === 0}
            loadingLabel="正在加载规则候选…"
            errorLabel="加载规则候选失败，请稍后重试。"
            emptyLabel="暂无规则候选。"
            searchLabel="搜索规则候选"
          />

          <div className="mt-5 grid gap-3">
            {sourceBuilds.map((row) => {
              const autonomousBuild = getAutonomousBuild(row)
              const probe = autonomousBuild?.probe
              const blockedByVerificationWall = probe?.content_status === 'verification_wall'
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
                  {blockedByVerificationWall ? <div className="mt-3 rounded-lg border border-rose-300 bg-rose-50 p-3 text-sm text-rose-700"><strong>正文访问受阻</strong>：检测到 verification wall，<strong>不可发布</strong>。</div> : null}
                </article>
              )
            })}
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
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground">Engine runs</p>
            <PaginatedListControls
              pagination={runsPagination}
              empty={!runsLoading && runs.length === 0}
              loadingLabel="正在加载运行记录…"
              errorLabel="加载运行记录失败，请稍后重试。"
              emptyLabel="暂无运行记录。"
              searchLabel="搜索运行"
            />
          </div>
          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground">Deployments</p>
            <PaginatedListControls
              pagination={deploymentsPagination}
              empty={!deploymentsLoading && deployments.length === 0}
              loadingLabel="正在加载部署记录…"
              errorLabel="加载部署记录失败，请稍后重试。"
              emptyLabel="暂无部署记录。"
              searchLabel="搜索部署"
            />
          </div>
        </div>
        <RunTimeline runs={runs} deployments={deployments} />
      </section>
    </ConsolePageShell>
  )
}
