import { ChangeEvent, FormEvent, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Upload } from 'lucide-react'

import { exportLegadoSources, importLegadoSourceFile, importLegadoSources, listBookSources, type LegadoSource, type SourceRow } from '@/api/modules/sources'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

const MAX_LEGADO_FILE_BYTES = 32 * 1024 * 1024
const SOURCE_PAGE_SIZE = 100

export function SourceListPage() {
  const [rows, setRows] = useState<SourceRow[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  const [legadoJson, setLegadoJson] = useState('')
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [readingFile, setReadingFile] = useState(false)
  const [createdVersionIds, setCreatedVersionIds] = useState<string[]>([])
  const mountedRef = useRef(true)
  const activeRequestIdRef = useRef(0)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const readingFileRef = useRef(false)
  const submittingRef = useRef(false)

  useEffect(() => {
    let mounted = true
    mountedRef.current = true
    void listBookSources({ page: 1, page_size: SOURCE_PAGE_SIZE }).then((response) => {
      if (mounted) {
        setRows(response.data)
        setPage(1)
        setTotal(Number(response.meta.total ?? response.data.length))
        setLoadError(null)
        setLoading(false)
      }
    }).catch(() => {
      if (mounted) {
        setLoadError('无法加载书源库存，请重试。')
        setLoading(false)
      }
    })
    return () => {
      mounted = false
      mountedRef.current = false
      activeRequestIdRef.current += 1
      readingFileRef.current = false
      submittingRef.current = false
    }
  }, [])

  function startRequest() {
    activeRequestIdRef.current += 1
    return activeRequestIdRef.current
  }

  function isCurrentRequest(requestId: number) {
    return mountedRef.current && activeRequestIdRef.current === requestId
  }

  async function handleLoadMore() {
    if (loading || loadingMore || rows.length >= total) return
    const nextPage = page + 1
    setLoadingMore(true)
    setLoadMoreError(null)
    try {
      const response = await listBookSources({ page: nextPage, page_size: SOURCE_PAGE_SIZE })
      if (!mountedRef.current) return
      setRows((current) => {
        const existingIds = new Set(current.map((item) => item.id))
        return [...current, ...response.data.filter((item) => !existingIds.has(item.id))]
      })
      setPage(nextPage)
      setTotal(Number(response.meta.total ?? total))
    } catch {
      if (mountedRef.current) setLoadMoreError('无法加载更多书源，请重试。')
    } finally {
      if (mountedRef.current) setLoadingMore(false)
    }
  }

  async function importLegadoJson(json: string, requestId: number) {
    if (!isCurrentRequest(requestId)) return
    setError(null); setFeedback(null); setCreatedVersionIds([])
    let parsed: unknown
    try { parsed = JSON.parse(json) } catch { setError('JSON 格式错误，请检查括号、逗号和引号。'); return }
    if (!Array.isArray(parsed) && (typeof parsed !== 'object' || parsed === null)) { setError('导入内容必须是一个书源对象或书源数组。'); return }
    if (!isCurrentRequest(requestId)) return
    submittingRef.current = true
    setSubmitting(true)
    try {
      const response = await importLegadoSources(parsed as LegadoSource | LegadoSource[])
      if (!isCurrentRequest(requestId)) return
      const created = response.data.items.filter((item) => item.status === 'created').length
      const invalid = response.data.items.filter((item) => item.status === 'invalid').length
      const skipped = response.data.items.filter((item) => item.status === 'skipped_duplicate').length
      setCreatedVersionIds(response.data.items.flatMap((item) => (
        item.status === 'created' && item.source_version_id ? [item.source_version_id] : []
      )))
      setFeedback(`已创建 ${created} 个候选书源${invalid ? `，${invalid} 项无效` : ''}${skipped ? `，${skipped} 项重复跳过` : ''}`)
      setLegadoJson('')
    } catch {
      if (isCurrentRequest(requestId)) setError('导入失败，请检查登录权限和书源内容。')
    } finally {
      if (isCurrentRequest(requestId)) {
        submittingRef.current = false
        setSubmitting(false)
      }
    }
  }

  function handleImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (readingFileRef.current || submittingRef.current) return
    void importLegadoJson(legadoJson, startRequest())
  }

  async function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (submittingRef.current) return
    const requestId = startRequest()
    readingFileRef.current = true
    setReadingFile(true)
    setError(null); setFeedback(null); setCreatedVersionIds([])
    if (!file) {
      if (isCurrentRequest(requestId)) {
        readingFileRef.current = false
        setReadingFile(false)
        setError('请选择一个 Legado JSON 文件。')
      }
      return
    }
    if (file.size > MAX_LEGADO_FILE_BYTES) {
      if (isCurrentRequest(requestId)) {
        readingFileRef.current = false
        setReadingFile(false)
        setError('JSON 文件超过 32 MiB 上传限制。')
      }
      return
    }
    try {
      const response = await importLegadoSourceFile(file)
      if (!isCurrentRequest(requestId)) return
      const created = response.data.items.filter((item) => item.status === 'created').length
      const invalid = response.data.items.filter((item) => item.status === 'invalid').length
      const skipped = response.data.items.filter((item) => item.status === 'skipped_duplicate').length
      setCreatedVersionIds(response.data.items.flatMap((item) => (
        item.status === 'created' && item.source_version_id ? [item.source_version_id] : []
      )))
      setFeedback(`已创建 ${created} 个候选书源${invalid ? `，${invalid} 项无效` : ''}${skipped ? `，${skipped} 项重复跳过` : ''}`)
      setLegadoJson('')
    } catch {
      if (isCurrentRequest(requestId)) setError('文件导入失败，请确认 JSON 格式、文件大小和登录权限。')
    } finally {
      if (isCurrentRequest(requestId)) {
        readingFileRef.current = false
        setReadingFile(false)
      }
    }
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

  return <ConsoleLayout eyebrow="书源" title="书源运行库存" description="查看当前运行中的书源。Legado JSON 导入始终作为候选版本，验证完成后才可发布。">
    <div className="flex justify-end"><Link to="/sources/health" className="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90">打开书源健康控制台</Link></div>
    <Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-semibold">Legado 书源导入与导出</h2><p className="mt-1 text-sm text-muted-foreground">导入仅创建候选书源，并移除 cookie、令牌和 Provider 等敏感字段。</p></div><Button type="button" variant="outline" onClick={() => void handleExport()}>导出可见书源</Button></div>
      <form className="mt-4 space-y-3" onSubmit={handleImport}><label className="text-sm font-medium" htmlFor="legado-json">Legado JSON</label><Textarea id="legado-json" value={legadoJson} onChange={(event) => setLegadoJson(event.target.value)} placeholder={'[{"bookSourceName":"示例书源","bookSourceUrl":"https://example.com"}]'} /><div className="flex flex-wrap items-end gap-3"><label className="sr-only" htmlFor="legado-json-file">选择 Legado JSON 文件</label><Input ref={fileInputRef} id="legado-json-file" className="sr-only" type="file" accept=".json,application/json" onChange={(event) => void handleFileSelection(event)} disabled={submitting || readingFile} /><Button type="button" variant="outline" disabled={submitting || readingFile} onClick={() => fileInputRef.current?.click()}><Upload className="mr-2 h-4 w-4" aria-hidden="true" />上传 JSON 文件</Button><Button type="submit" disabled={submitting || readingFile}>导入书源</Button>{feedback ? <span className="pb-2 text-sm text-emerald-600">{feedback}</span> : null}{error ? <span role="alert" className="pb-2 text-sm text-rose-600">{error}</span> : null}</div>{createdVersionIds.length > 0 ? <div className="mt-3 flex flex-wrap items-center gap-2 text-sm"><span className="text-muted-foreground">候选书源已创建，可继续：</span>{createdVersionIds.map((sourceVersionId) => <Link key={sourceVersionId} to={`/sources/rules/${sourceVersionId}`} className="font-medium text-primary underline-offset-4 hover:underline">编辑规则</Link>)}</div> : null}</form>
    </Card>
    <div className="grid gap-4">{loading ? <Card className="p-6 text-sm text-muted-foreground">正在加载书源…</Card> : loadError ? <Card className="p-6 text-sm text-rose-600" role="alert">{loadError}</Card> : rows.length === 0 ? <Card className="p-6 text-sm text-muted-foreground">当前运行库存中还没有书源。可上传 Legado JSON 文件创建候选书源。</Card> : <>{rows.map((row) => <Card key={row.id} className="grid gap-4 p-5 md:grid-cols-[1.6fr_1fr]"><div><p className="text-xs font-medium text-muted-foreground">书源</p><h3 className="mt-2 text-lg font-semibold">{row.bookSourceName}</h3><p className="mt-2 break-all text-sm text-muted-foreground">{row.bookSourceUrl}</p></div><div className="rounded-md border border-border bg-muted/40 p-4"><p className="text-xs font-medium text-muted-foreground">书源状态</p><p className="mt-2 text-lg font-medium text-primary">{row.sourceStatus}</p>{row.sourceStatus === 'candidate' ? <Link to={`/sources/rules/${row.id}`} className="mt-3 inline-flex text-sm font-medium text-primary underline-offset-4 hover:underline">审核规则</Link> : null}</div></Card>)}<div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-muted-foreground">已显示 {rows.length} / {total} 个书源</p>{rows.length < total ? <Button type="button" variant="outline" onClick={() => void handleLoadMore()} disabled={loadingMore}>{loadingMore ? '正在加载…' : '加载更多书源'}</Button> : null}</div>{loadMoreError ? <p role="alert" className="text-sm text-rose-600">{loadMoreError}</p> : null}</>}</div>
  </ConsoleLayout>
}
