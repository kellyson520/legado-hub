import { ChangeEvent, FormEvent, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Upload } from 'lucide-react'

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
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [legadoJson, setLegadoJson] = useState('')
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [readingFile, setReadingFile] = useState(false)
  const [createdVersionIds, setCreatedVersionIds] = useState<string[]>([])
  const mountedRef = useRef(true)
  const activeRequestIdRef = useRef(0)
  const latestLoadRequestIdRef = useRef(0)
  const displayedPageRef = useRef(1)
  const appliedSearchRef = useRef('')
  const retryRequestRef = useRef({ page: 1, search: '' })
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const readingFileRef = useRef(false)
  const submittingRef = useRef(false)

  function startLoadRequest() {
    latestLoadRequestIdRef.current += 1
    return latestLoadRequestIdRef.current
  }

  function isCurrentLoadRequest(requestId: number) {
    return mountedRef.current && latestLoadRequestIdRef.current === requestId
  }

  async function loadPage(requestedPage: number, requestedSearch = appliedSearchRef.current) {
    if (!mountedRef.current) return
    const requestId = startLoadRequest()
    retryRequestRef.current = { page: requestedPage, search: requestedSearch }
    setLoading(true)
    setLoadError(null)
    try {
      const response = await listBookSources({
        page: requestedPage,
        page_size: SOURCE_PAGE_SIZE,
        search: requestedSearch,
      })
      if (!isCurrentLoadRequest(requestId)) return
      const responsePage = Number(response.meta.page)
      const nextPage = Number.isInteger(responsePage) && responsePage >= 1 ? responsePage : requestedPage
      const responseTotal = Number(response.meta.total)
      const nextTotal = Number.isFinite(responseTotal) && responseTotal >= 0 ? responseTotal : response.data.length
      setRows(response.data)
      setPage(nextPage)
      setTotal(nextTotal)
      displayedPageRef.current = nextPage
    } catch {
      if (isCurrentLoadRequest(requestId)) setLoadError('无法加载书源库存，请重试。')
    } finally {
      if (isCurrentLoadRequest(requestId)) setLoading(false)
    }
  }

  useEffect(() => {
    mountedRef.current = true
    appliedSearchRef.current = ''
    void loadPage(1, '')
    return () => {
      mountedRef.current = false
      activeRequestIdRef.current += 1
      latestLoadRequestIdRef.current += 1
      readingFileRef.current = false
      submittingRef.current = false
    }
  }, [])

  function startActionRequest() {
    activeRequestIdRef.current += 1
    return activeRequestIdRef.current
  }

  function isCurrentRequest(requestId: number) {
    return mountedRef.current && activeRequestIdRef.current === requestId
  }

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextSearch = search.trim()
    setAppliedSearch(nextSearch)
    appliedSearchRef.current = nextSearch
    void loadPage(1, nextSearch)
  }

  function handleClearSearch() {
    if (!search && !appliedSearch) return
    setSearch('')
    setAppliedSearch('')
    appliedSearchRef.current = ''
    void loadPage(1, '')
  }

  function handlePageChange(nextPage: number) {
    const totalPages = Math.max(1, Math.ceil(total / SOURCE_PAGE_SIZE))
    if (loading || nextPage < 1 || nextPage > totalPages || nextPage === page) return
    void loadPage(nextPage, appliedSearchRef.current)
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
    void importLegadoJson(legadoJson, startActionRequest())
  }

  async function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (submittingRef.current) return
    const requestId = startActionRequest()
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

  const totalPages = Math.max(1, Math.ceil(total / SOURCE_PAGE_SIZE))

  return <ConsoleLayout eyebrow="书源" title="书源运行库存" description="查看当前运行中的书源。Legado JSON 导入始终作为候选版本，验证完成后才可发布。">
    <div className="flex justify-end"><Link to="/sources/health" className="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90">打开书源健康控制台</Link></div>
    <Card className="p-5">
      <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={handleSearch}>
        <div className="min-w-0 flex-1">
          <label className="text-sm font-medium" htmlFor="source-search">搜索书源</label>
          <Input id="source-search" aria-label="搜索书源" className="mt-2" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="按名称、URL 或规则搜索" />
        </div>
        <div className="flex gap-2">
          <Button type="submit" disabled={loading}><Search className="mr-2 h-4 w-4" aria-hidden="true" />搜索</Button>
          <Button type="button" variant="outline" onClick={handleClearSearch} disabled={loading || (!search && !appliedSearch)}>清空</Button>
        </div>
      </form>
    </Card>
    <Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-semibold">Legado 书源导入与导出</h2><p className="mt-1 text-sm text-muted-foreground">导入仅创建候选书源，并移除 cookie、令牌和 Provider 等敏感字段。</p></div><Button type="button" variant="outline" onClick={() => void handleExport()}>导出可见书源</Button></div>
      <form className="mt-4 space-y-3" onSubmit={handleImport}><label className="text-sm font-medium" htmlFor="legado-json">Legado JSON</label><Textarea id="legado-json" value={legadoJson} onChange={(event) => setLegadoJson(event.target.value)} placeholder={'[{"bookSourceName":"示例书源","bookSourceUrl":"https://example.com"}]'} /><div className="flex flex-wrap items-end gap-3"><label className="sr-only" htmlFor="legado-json-file">选择 Legado JSON 文件</label><Input ref={fileInputRef} id="legado-json-file" className="sr-only" type="file" accept=".json,application/json" onChange={(event) => void handleFileSelection(event)} disabled={submitting || readingFile} /><Button type="button" variant="outline" disabled={submitting || readingFile} onClick={() => fileInputRef.current?.click()}><Upload className="mr-2 h-4 w-4" aria-hidden="true" />上传 JSON 文件</Button><Button type="submit" disabled={submitting || readingFile}>导入书源</Button>{feedback ? <span className="pb-2 text-sm text-emerald-600">{feedback}</span> : null}{error ? <span role="alert" className="pb-2 text-sm text-rose-600">{error}</span> : null}</div>{createdVersionIds.length > 0 ? <div className="mt-3 flex flex-wrap items-center gap-2 text-sm"><span className="text-muted-foreground">候选书源已创建，可继续：</span>{createdVersionIds.map((sourceVersionId) => <Link key={sourceVersionId} to={`/sources/rules/${sourceVersionId}`} className="font-medium text-primary underline-offset-4 hover:underline">编辑规则</Link>)}</div> : null}</form>
    </Card>
    <div className="grid gap-4">
      {loading ? <Card className="p-6 text-sm text-muted-foreground">正在加载书源…</Card> : loadError ? <Card className="flex flex-wrap items-center gap-3 p-6 text-sm text-rose-600" role="alert"><span>{loadError}</span><Button type="button" variant="outline" size="sm" onClick={() => void loadPage(retryRequestRef.current.page, retryRequestRef.current.search)}>重试</Button></Card> : rows.length === 0 ? <Card className="p-6 text-sm text-muted-foreground">{appliedSearch ? `没有匹配“${appliedSearch}”的书源。` : '当前运行库存中还没有书源。可上传 Legado JSON 文件创建候选书源。'}</Card> : <>
        {rows.map((row) => <Card key={row.id} className="grid gap-4 p-5 md:grid-cols-[1.6fr_1fr]"><div><p className="text-xs font-medium text-muted-foreground">书源</p><h3 className="mt-2 text-lg font-semibold">{row.bookSourceName}</h3><p className="mt-2 break-all text-sm text-muted-foreground">{row.bookSourceUrl}</p></div><div className="rounded-md border border-border bg-muted/40 p-4"><p className="text-xs font-medium text-muted-foreground">书源状态</p><p className="mt-2 text-lg font-medium text-primary">{row.sourceStatus}</p>{row.sourceStatus === 'candidate' ? <Link to={`/sources/rules/${row.id}`} className="mt-3 inline-flex text-sm font-medium text-primary underline-offset-4 hover:underline">审核规则</Link> : null}</div></Card>)}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-card p-4"><p className="text-sm text-muted-foreground">第 {page} / {totalPages} 页，共 {total} 个书源</p><div className="flex gap-2"><Button type="button" variant="outline" onClick={() => handlePageChange(page - 1)} disabled={loading || page <= 1}>上一页</Button><Button type="button" variant="outline" onClick={() => handlePageChange(page + 1)} disabled={loading || page >= totalPages}>下一页</Button></div></div>
      </>}
    </div>
  </ConsoleLayout>
}
