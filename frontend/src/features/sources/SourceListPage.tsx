import { FormEvent, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { exportLegadoSources, importLegadoSources, listBookSources, type SourceRow } from '@/api/modules/sources'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'

export function SourceListPage() {
  const [rows, setRows] = useState<SourceRow[]>([])
  const [loading, setLoading] = useState(true)
  const [legadoJson, setLegadoJson] = useState('')
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let mounted = true
    void listBookSources({ page: 1, page_size: 20 }).then((response) => {
      if (mounted) { setRows(response.data); setLoading(false) }
    })
    return () => { mounted = false }
  }, [])

  async function handleImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null); setFeedback(null)
    let parsed: unknown
    try { parsed = JSON.parse(legadoJson) } catch { setError('JSON 格式错误，请检查括号、逗号和引号。'); return }
    if (!Array.isArray(parsed) && (typeof parsed !== 'object' || parsed === null)) { setError('导入内容必须是一个书源对象或书源数组。'); return }
    setSubmitting(true)
    try {
      const response = await importLegadoSources(parsed as never)
      const created = response.data.items.filter((item) => item.status === 'created').length
      const invalid = response.data.items.filter((item) => item.status === 'invalid').length
      const skipped = response.data.items.filter((item) => item.status === 'skipped_duplicate').length
      setFeedback(`已创建 ${created} 个候选书源${invalid ? `，${invalid} 项无效` : ''}${skipped ? `，${skipped} 项重复跳过` : ''}`)
      setLegadoJson('')
    } catch { setError('导入失败，请检查登录权限和书源内容。') } finally { setSubmitting(false) }
  }

  async function handleExport() {
    setError(null)
    try {
      const response = await exportLegadoSources()
      const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json;charset=utf-8' })
      const url = URL.createObjectURL(blob); const link = document.createElement('a')
      link.href = url; link.download = 'legado-book-sources.json'; link.click(); URL.revokeObjectURL(url)
      setFeedback(`已导出 ${response.data.length} 个可见书源。`)
    } catch { setError('导出失败，请检查登录权限。') }
  }

  return <ConsoleLayout eyebrow="书源" title="书源运行库存" description="查看已发布书源与候选版本。Legado JSON 导入始终作为候选版本，验证完成后才可发布。">
    <div className="flex justify-end"><Link to="/sources/health" className="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90">打开书源健康控制台</Link></div>
    <Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-semibold">Legado 书源导入与导出</h2><p className="mt-1 text-sm text-muted-foreground">导入仅创建候选书源，并移除 cookie、令牌和 Provider 等敏感字段。</p></div><Button type="button" variant="outline" onClick={() => void handleExport()}>导出可见书源</Button></div>
      <form className="mt-4 space-y-3" onSubmit={handleImport}><label className="text-sm font-medium" htmlFor="legado-json">Legado JSON</label><Textarea id="legado-json" value={legadoJson} onChange={(event) => setLegadoJson(event.target.value)} placeholder={'[{"bookSourceName":"示例书源","bookSourceUrl":"https://example.com"}]'} /><div className="flex flex-wrap items-center gap-3"><Button type="submit" disabled={submitting}>导入书源</Button>{feedback ? <span className="text-sm text-emerald-600">{feedback}</span> : null}{error ? <span className="text-sm text-rose-600">{error}</span> : null}</div></form>
    </Card>
    <div className="grid gap-4">{loading ? <Card className="p-6 text-sm text-muted-foreground">正在加载书源…</Card> : rows.map((row) => <Card key={row.id} className="grid gap-4 p-5 md:grid-cols-[1.6fr_1fr_1fr]"><div><p className="text-xs font-medium text-muted-foreground">书源</p><h3 className="mt-2 text-lg font-semibold">{row.name}</h3><p className="mt-2 text-sm text-muted-foreground">状态：{row.status}</p></div><div className="rounded-md border border-border bg-muted/40 p-4"><p className="text-xs font-medium text-muted-foreground">已发布版本</p><p className="mt-2 text-lg font-medium text-primary">{row.publishedVersion}</p></div><div className="rounded-md border border-border bg-muted/40 p-4"><p className="text-xs font-medium text-muted-foreground">最近评分</p><p className="mt-2 text-lg font-medium text-emerald-600">{row.latestGrade}</p></div></Card>)}</div>
  </ConsoleLayout>
}
