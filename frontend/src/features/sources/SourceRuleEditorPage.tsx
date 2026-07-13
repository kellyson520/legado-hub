import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { useAuth } from '@/app/providers/AuthProvider'
import {
  createSourceDraft,
  getSourceVersion,
  publishSourceVersion,
  validateSourceVersion,
  type SourceVersionResponse,
} from '@/api/modules/sources'
import { testEngineRegex, type RegexTestResult } from '@/api/modules/engine'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

function getRules(payload: Record<string, unknown>) {
  return Object.fromEntries(
    Object.entries(payload).filter(([key]) => key !== 'bookSourceName' && key !== 'bookSourceUrl')
  )
}

function parseRules(value: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(value)
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : null
  } catch {
    return null
  }
}

function versionFromResponse(response: { data: SourceVersionResponse }) {
  return response.data
}

export function SourceRuleEditorPage() {
  const { sourceVersionId = '' } = useParams()
  const navigate = useNavigate()
  const { hasPermission } = useAuth()
  const canWrite = hasPermission('book_sources.write')
  const [version, setVersion] = useState<SourceVersionResponse | null>(null)
  const [bookSourceName, setBookSourceName] = useState('')
  const [bookSourceUrl, setBookSourceUrl] = useState('')
  const [rulesJson, setRulesJson] = useState('{}')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [regexText, setRegexText] = useState('')
  const [regexPattern, setRegexPattern] = useState('')
  const [regexReplacement, setRegexReplacement] = useState('')
  const [regexResult, setRegexResult] = useState<RegexTestResult | null>(null)

  useEffect(() => {
    let active = true

    async function loadVersion() {
      setLoading(true)
      setError(null)
      try {
        const response = await getSourceVersion(sourceVersionId)
        if (!active) return
        const next = versionFromResponse(response)
        setVersion(next)
        setBookSourceName(String(next.payload.bookSourceName ?? next.source_id))
        setBookSourceUrl(String(next.payload.bookSourceUrl ?? ''))
        setRulesJson(JSON.stringify(getRules(next.payload), null, 2))
      } catch {
        if (active) setError('加载书源版本失败，请确认版本标识和访问权限。')
      } finally {
        if (active) setLoading(false)
      }
    }

    if (sourceVersionId) void loadVersion()
    else {
      setError('缺少书源版本标识。')
      setLoading(false)
    }

    return () => { active = false }
  }, [sourceVersionId])

  const parsedRules = useMemo(() => parseRules(rulesJson), [rulesJson])
  const rulesJsonInvalid = parsedRules === null
  const contentBlocked = version?.content_status === 'verification_wall'
  const publishEnabled = Boolean(canWrite && version?.publish_allowed && !contentBlocked)

  async function handleSaveDraft() {
    if (!parsedRules || !canWrite) return
    setSubmitting(true)
    setError(null)
    setMessage(null)
    try {
      const response = await createSourceDraft(sourceVersionId, {
        bookSourceName,
        bookSourceUrl,
        ...parsedRules,
      })
      const next = versionFromResponse(response)
      setMessage('已保存为候选版本。')
      navigate(`/sources/rules/${next.source_version_id}`)
    } catch {
      setError('保存候选版本失败，请检查规则内容和写入权限。')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleValidate() {
    if (!canWrite) return
    setSubmitting(true)
    setError(null)
    setMessage(null)
    try {
      const response = await validateSourceVersion(sourceVersionId)
      setVersion(versionFromResponse(response))
      setMessage('规则验证已完成。')
    } catch {
      setError('规则验证失败，请检查书源网络状态与规则配置。')
    } finally {
      setSubmitting(false)
    }
  }

  async function handlePublish() {
    if (!publishEnabled) return
    setSubmitting(true)
    setError(null)
    setMessage(null)
    try {
      const response = await publishSourceVersion(sourceVersionId)
      setVersion(versionFromResponse(response))
      setMessage('候选版本已发布。')
    } catch {
      setError('发布被拒绝：请先通过完整验证。')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRegexTest() {
    if (!regexPattern.trim()) return
    setError(null)
    setRegexResult(null)
    try {
      const response = await testEngineRegex({
        text: regexText,
        pattern: regexPattern,
        replacement: regexReplacement || null,
      })
      setRegexResult(response.data)
    } catch {
      setError('正则测试失败，请检查表达式。')
    }
  }

  return (
    <ConsoleLayout
      eyebrow="书源规则"
      title="书源规则编辑器"
      description="编辑候选书源的搜索、目录与正文规则；保存后必须完成验证，正文访问受阻的版本不能发布。"
      actions={<Button asChild variant="outline"><Link to="/sources">返回书源库</Link></Button>}
    >
      {loading ? <Card className="p-6 text-sm text-muted-foreground">正在加载书源版本…</Card> : null}
      {error ? <p role="alert" className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p> : null}
      {message ? <p className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{message}</p> : null}

      {!loading && version ? (
        <div className="grid gap-5">
          <Card className="grid gap-4 p-5 md:grid-cols-2">
            <label className="grid gap-2 text-sm font-medium" htmlFor="book-source-name">
              书源名称
              <Input id="book-source-name" value={bookSourceName} onChange={(event) => setBookSourceName(event.target.value)} disabled={!canWrite} />
            </label>
            <label className="grid gap-2 text-sm font-medium" htmlFor="book-source-url">
              书源地址
              <Input id="book-source-url" value={bookSourceUrl} onChange={(event) => setBookSourceUrl(event.target.value)} disabled={!canWrite} />
            </label>
            <div className="md:col-span-2 text-sm text-muted-foreground">
              当前版本：{version.source_version_id} · 状态：{version.status} · 正文状态：{version.content_status}
            </div>
          </Card>

          <Card className="space-y-4 p-5">
            <div>
              <h2 className="text-lg font-semibold">规则 JSON</h2>
              <p className="mt-1 text-sm text-muted-foreground">填写 ruleSearch、ruleToc、ruleContent、ruleBookInfo 等 Legado 规则字段。</p>
            </div>
            <label className="sr-only" htmlFor="source-rules-json">规则 JSON</label>
            <Textarea
              id="source-rules-json"
              aria-label="规则 JSON"
              className="min-h-[360px] font-mono"
              value={rulesJson}
              onChange={(event) => setRulesJson(event.target.value)}
              disabled={!canWrite}
            />
            {rulesJsonInvalid ? <p className="text-sm text-rose-600">规则 JSON 格式错误，修正后才能保存候选版本。</p> : null}
            {!canWrite ? <p className="text-sm text-amber-700">当前账户仅有查看权限，不能保存、验证或发布规则。</p> : null}
            {contentBlocked ? <p className="text-sm font-medium text-rose-700">正文访问受阻，禁止发布</p> : null}
            <div className="flex flex-wrap gap-3">
              <Button type="button" onClick={() => void handleSaveDraft()} disabled={!canWrite || rulesJsonInvalid || submitting}>保存候选</Button>
              <Button type="button" variant="outline" onClick={() => void handleValidate()} disabled={!canWrite || submitting}>验证规则</Button>
              {canWrite ? <Button type="button" variant="secondary" onClick={() => void handlePublish()} disabled={!publishEnabled || submitting}>发布版本</Button> : null}
            </div>
          </Card>

          {version.latest_validation ? (
            <Card className="space-y-3 p-5">
              <h2 className="text-lg font-semibold">最近验证结果</h2>
              <p className="text-sm">评分：{version.latest_validation.score} · 等级：{version.latest_validation.grade}</p>
              <div className="grid gap-2 md:grid-cols-3">
                {Object.entries(version.latest_validation.step_results).map(([step, result]) => (
                  <div key={step} className="rounded-md border border-border p-3 text-sm">
                    <p className="font-medium">{step}</p>
                    <p className={result.passed ? 'text-emerald-600' : 'text-rose-600'}>{result.passed ? '通过' : '失败'} · {result.status ?? 'unknown'}</p>
                  </div>
                ))}
              </div>
              {version.latest_validation.diagnostics.length > 0 ? (
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  {version.latest_validation.diagnostics.map((diagnostic, index) => <li key={`${diagnostic}-${index}`}>{diagnostic}</li>)}
                </ul>
              ) : null}
            </Card>
          ) : null}

          <Card className="space-y-4 p-5">
            <div>
              <h2 className="text-lg font-semibold">正则测试工具</h2>
              <p className="mt-1 text-sm text-muted-foreground">在保存规则前测试提取表达式与替换结果。</p>
            </div>
            <label className="grid gap-2 text-sm font-medium" htmlFor="regex-pattern">正则表达式<Input id="regex-pattern" value={regexPattern} onChange={(event) => setRegexPattern(event.target.value)} /></label>
            <label className="grid gap-2 text-sm font-medium" htmlFor="regex-replacement">替换文本（可选）<Input id="regex-replacement" value={regexReplacement} onChange={(event) => setRegexReplacement(event.target.value)} /></label>
            <label className="grid gap-2 text-sm font-medium" htmlFor="regex-text">测试文本<Textarea id="regex-text" value={regexText} onChange={(event) => setRegexText(event.target.value)} /></label>
            <Button type="button" variant="outline" onClick={() => void handleRegexTest()} disabled={!regexPattern.trim()}>测试正则</Button>
            {regexResult ? (
              <div className="rounded-md border border-border bg-muted/40 p-4 text-sm">
                <p>匹配数量：{regexResult.match_count}</p>
                {regexResult.error ? <p className="mt-2 text-rose-600">{regexResult.error}</p> : null}
                {regexResult.replacement_preview !== null ? <pre className="mt-2 whitespace-pre-wrap text-muted-foreground">{regexResult.replacement_preview}</pre> : null}
              </div>
            ) : null}
          </Card>
        </div>
      ) : null}
    </ConsoleLayout>
  )
}
