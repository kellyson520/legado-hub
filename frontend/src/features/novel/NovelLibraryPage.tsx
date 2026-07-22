import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowUpRight, BookOpen, Check, FileUp, Loader2, Search, Sparkles, UploadCloud } from 'lucide-react'

import {
  createNovelConversation,
  getNovelBook,
  importNovelFromSource,
  importNovelFromUrl,
  listNovelBooks,
  listNovelChapters,
  searchNovelBooks,
  uploadNovel,
  type NovelBook,
  type NovelChapter,
  type NovelSearchResult,
} from '@/api/modules/novel'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

const statusLabel: Record<string, string> = {
  pending: '等待处理',
  ingesting: '正在摄入',
  summarizing: '正在理解',
  ready: '可阅读',
  failed: '需要重试',
  error: '分析失败，可重试',
}

function percentOf(book: NovelBook) {
  const value = book.progress?.percent ?? book.ingest_progress ?? 0
  return Math.round(Math.max(0, Math.min(1, Number(value))) * 100)
}

function formatDate(value?: string) {
  if (!value) return '刚刚更新'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '刚刚更新' : date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function coverLetter(book: NovelBook) {
  return Array.from(book.book_name.trim())[0] || '书'
}

function bookChapter(book: NovelBook) {
  return book.progress?.chapter_title || (book.progress?.chapter_id ? `第 ${book.progress.chapter_id} 章` : '尚未开始')
}

export function NovelLibraryPage() {
  const { bookId } = useParams<{ bookId?: string }>()
  const navigate = useNavigate()
  const uploadInput = useRef<HTMLInputElement>(null)
  const [books, setBooks] = useState<NovelBook[]>([])
  const [selectedBook, setSelectedBook] = useState<NovelBook | null>(null)
  const [chapters, setChapters] = useState<NovelChapter[]>([])
  const [keyword, setKeyword] = useState('')
  const [url, setUrl] = useState('')
  const [searchResults, setSearchResults] = useState<NovelSearchResult[]>([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [busyKey, setBusyKey] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const loadBooks = async () => {
    setLoading(true)
    try {
      const response = await listNovelBooks()
      setBooks(response.data)
      setError('')
    } catch {
      setError('书架暂时无法加载，请稍后重试。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadBooks()
  }, [])

  useEffect(() => {
    if (!bookId) {
      setSelectedBook(null)
      setChapters([])
      return
    }
    const detailBookId = bookId
    let mounted = true
    async function loadDetail() {
      try {
        const [bookResponse, chapterResponse] = await Promise.all([
          getNovelBook(detailBookId),
          listNovelChapters(detailBookId),
        ])
        if (!mounted) return
        setSelectedBook(bookResponse.data)
        setChapters(chapterResponse.data)
      } catch {
        if (mounted) setError('书籍详情暂时无法加载。')
      }
    }
    void loadDetail()
    return () => {
      mounted = false
    }
  }, [bookId])

  const currentBook = useMemo(() => {
    if (!bookId) return null
    return selectedBook ?? books.find((book) => String(book.id) === bookId) ?? null
  }, [bookId, books, selectedBook])

  const search = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!keyword.trim() || searching) return
    setSearching(true)
    setNotice('')
    try {
      const response = await searchNovelBooks(keyword)
      setSearchResults(response.data)
      setError('')
    } catch {
      setError('搜书失败，请检查书源状态后重试。')
    } finally {
      setSearching(false)
    }
  }

  const addFromSource = async (result: NovelSearchResult) => {
    const key = `${result.sourceId}:${result.bookUrl}`
    setBusyKey(key)
    try {
      await importNovelFromSource({
        sourceId: result.sourceId,
        bookUrl: result.bookUrl,
        name: result.name,
        author: result.author,
      })
      setNotice(`导入任务已创建：${result.name}`)
      await loadBooks()
    } catch {
      setError(`无法导入《${result.name}》，请稍后重试。`)
    } finally {
      setBusyKey('')
    }
  }

  const handleUpload = async (file?: File) => {
    if (!file) return
    setBusyKey(`upload:${file.name}`)
    setNotice('')
    try {
      await uploadNovel(file)
      setNotice(`导入任务已创建：${file.name}`)
      await loadBooks()
    } catch {
      setError(`无法读取 ${file.name}，支持 TXT、Markdown、HTML 和 EPUB。`)
    } finally {
      setBusyKey('')
      if (uploadInput.current) uploadInput.current.value = ''
    }
  }

  const importUrl = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!url.trim() || busyKey) return
    setBusyKey('url')
    try {
      await importNovelFromUrl(url.trim())
      setNotice('导入任务已创建：网络链接')
      setUrl('')
      await loadBooks()
    } catch {
      setError('链接解析失败，请确认地址可访问且符合系统安全策略。')
    } finally {
      setBusyKey('')
    }
  }

  const openBookAssistant = async () => {
    if (!currentBook) return
    try {
      const response = await createNovelConversation({ bookId: currentBook.id, entrypoint: 'book', title: `《${currentBook.book_name}》助手` })
      navigate(`/ai/workspace?conversation=${encodeURIComponent(response.data.id)}&bookId=${currentBook.id}`)
    } catch {
      setError('助手会话暂时无法打开。')
    }
  }

  return (
    <ConsoleLayout
      eyebrow="NOVEL / SHELF"
      title={currentBook ? currentBook.book_name : '我的书架'}
      description={currentBook ? '书籍详情、章节索引与 Agent 上下文共用同一本书的持久化数据。' : '把上传、书源与网络链接收进同一张书架，进度和理解索引会随书保存。'}
      actions={currentBook ? <Button variant="outline" onClick={() => navigate('/novel/library')}>返回书架</Button> : <Link to="/novel/tasks" className="text-sm text-muted-foreground underline-offset-4 hover:underline">查看索引任务</Link>}
    >
      {error ? <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</p> : null}
      {notice ? <p role="status" className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">{notice}</p> : null}

      {currentBook ? (
        <section className="space-y-5">
          <Card className="overflow-hidden border-0 bg-[linear-gradient(115deg,hsl(var(--primary)/.12),transparent_55%),hsl(var(--card))] shadow-sm">
            <div className="grid gap-6 p-6 md:grid-cols-[112px_minmax(0,1fr)_auto] md:items-center">
              <div className="grid aspect-[3/4] place-items-center rounded-lg bg-primary text-4xl font-semibold text-primary-foreground shadow-lg shadow-primary/20" aria-hidden="true">{coverLetter(currentBook)}</div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">Book dossier</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight">{currentBook.book_name}</h2>
                <p className="mt-2 text-sm text-muted-foreground">{currentBook.author || '作者未标注'} · {currentBook.source_name || '本地内容'}</p>
                <p className="mt-4 max-w-2xl text-sm leading-7 text-muted-foreground">{currentBook.summary_global || '这本书还没有生成全书摘要。阅读和提问会持续补齐理解索引。'}</p>
              </div>
              <div className="flex flex-wrap gap-2 md:flex-col">
                <Button onClick={openBookAssistant}><Sparkles className="mr-2 h-4 w-4" aria-hidden="true" />问助手</Button>
                <Link to={`/novel/books/${currentBook.id}/read/${currentBook.progress?.chapter_id ?? chapters[0]?.id ?? 1}`} className="inline-flex h-10 items-center justify-center rounded-md border border-input bg-card px-4 text-sm font-medium hover:bg-accent">开始阅读</Link>
              </div>
            </div>
          </Card>
          <section aria-labelledby="chapter-index-title" className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Index</p><h2 id="chapter-index-title" className="mt-1 text-lg font-semibold">章节索引</h2></div>
              <span className="text-sm text-muted-foreground">{chapters.length} 章</span>
            </div>
            <ol className="divide-y divide-border">
              {chapters.map((chapter) => (
                <li key={chapter.id}>
                  <Link to={`/novel/books/${currentBook.id}/read/${chapter.id}`} className="flex items-center justify-between gap-4 px-5 py-4 text-sm hover:bg-accent/50">
                    <span><span className="mr-3 font-mono text-xs text-muted-foreground">{chapter.canonical_full || `C${chapter.chapter_num ?? ''}`}</span>{chapter.chapter_title}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">{chapter.word_count ? `${chapter.word_count.toLocaleString()} 字` : '未统计'}</span>
                  </Link>
                </li>
              ))}
              {!chapters.length ? <li className="px-5 py-8 text-center text-sm text-muted-foreground">章节正在摄入，稍后刷新。</li> : null}
            </ol>
          </section>
        </section>
      ) : (
        <>
          <section className="grid gap-4 rounded-2xl border border-border bg-[linear-gradient(120deg,hsl(var(--primary)/.13),transparent_42%),hsl(var(--card))] p-5 shadow-sm md:grid-cols-[1fr_auto] md:items-end md:p-7">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Reading room / 01</p>
              <h2 className="mt-3 max-w-xl text-3xl font-semibold tracking-tight md:text-4xl">把故事放回它该在的地方。</h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground">每一本书都有自己的进度、章节证据和 Agent 记忆。你可以从任何入口回来，接着读，也接着问。</p>
            </div>
            <div className="flex items-center gap-5 border-t border-border/70 pt-4 md:border-l md:border-t-0 md:pl-6 md:pt-0">
              <div><p className="font-mono text-2xl font-semibold">{books.length}</p><p className="text-xs text-muted-foreground">书架藏书</p></div>
              <div><p className="font-mono text-2xl font-semibold">{books.filter((book) => book.status === 'ready').length}</p><p className="text-xs text-muted-foreground">可继续阅读</p></div>
            </div>
          </section>

          <section aria-label="导入与搜书" className="grid gap-3 rounded-xl border border-border bg-card p-4 lg:grid-cols-[minmax(0,1fr)_auto_auto] lg:items-end">
            <form onSubmit={search} className="flex gap-2">
              <label className="min-w-0 flex-1"><span className="mb-1 block text-xs font-medium text-muted-foreground">从已配置书源找书</span><div className="relative"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" /><Input aria-label="搜索书名" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="输入书名或作者…" className="pl-9" /></div></label>
              <Button type="submit" className="mt-5" disabled={searching || !keyword.trim()}>{searching ? <Loader2 className="h-4 w-4 animate-spin" aria-label="正在搜索" /> : '搜书'}</Button>
            </form>
            <label className="mt-5 inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-md border border-input bg-card px-4 text-sm font-medium hover:bg-accent"><UploadCloud className="h-4 w-4" aria-hidden="true" />上传小说<input ref={uploadInput} aria-label="上传小说" type="file" accept=".txt,.md,.markdown,.html,.htm,.epub,text/plain,text/markdown,text/html,application/epub+zip" className="sr-only" onChange={(event) => void handleUpload(event.target.files?.[0])} /></label>
            <form onSubmit={importUrl} className="flex gap-2 lg:max-w-[330px]">
              <label className="min-w-0 flex-1"><span className="mb-1 block text-xs font-medium text-muted-foreground">解析网络链接</span><Input aria-label="网络链接" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://…" inputMode="url" /></label>
              <Button type="submit" variant="outline" className="mt-5" disabled={!url.trim() || Boolean(busyKey)}>解析</Button>
            </form>
          </section>

          {searchResults.length ? (
            <section aria-labelledby="search-results-title" className="rounded-xl border border-primary/25 bg-primary/[.04] p-4">
              <div className="mb-3 flex items-center justify-between"><h2 id="search-results-title" className="text-sm font-semibold">书源搜索结果</h2><button type="button" className="text-xs text-muted-foreground underline-offset-4 hover:underline" onClick={() => setSearchResults([])}>收起</button></div>
              <div className="grid gap-3 md:grid-cols-2">
                {searchResults.map((result) => {
                  const key = `${result.sourceId}:${result.bookUrl}`
                  return <article key={key} className="flex items-center justify-between gap-4 rounded-lg border border-border bg-card p-4"><div className="min-w-0"><h3 className="truncate font-medium">{result.name}</h3><p className="mt-1 truncate text-xs text-muted-foreground">{result.author || '作者未知'} · {result.sourceName || '已配置书源'}</p></div><Button size="sm" onClick={() => void addFromSource(result)} disabled={busyKey === key}>{busyKey === key ? <Loader2 className="h-4 w-4 animate-spin" aria-label="正在导入" /> : <><FileUp className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />加入书架</>}</Button></article>
                })}
              </div>
            </section>
          ) : null}

          <section aria-labelledby="shelf-title">
            <div className="mb-3 flex items-end justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Your shelf</p><h2 id="shelf-title" className="mt-1 text-xl font-semibold">最近阅读</h2></div><span className="text-xs text-muted-foreground">按最近更新排序</span></div>
            {loading ? <p className="rounded-xl border border-dashed border-border px-5 py-10 text-center text-sm text-muted-foreground">正在整理书架…</p> : null}
            {!loading && !books.length ? <div className="rounded-xl border border-dashed border-border px-5 py-12 text-center"><BookOpen className="mx-auto h-8 w-8 text-primary" aria-hidden="true" /><p className="mt-3 font-medium">书架还是空的</p><p className="mt-1 text-sm text-muted-foreground">上传一本小说、搜一本书，阅读室就会亮起来。</p></div> : null}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {books.map((book) => {
                const percent = percentOf(book)
                return <Card key={book.id} className="group overflow-hidden transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-lg">
                  <div className="flex gap-4 p-4">
                    <div className="grid h-28 w-20 shrink-0 place-items-center rounded-md bg-primary/90 text-3xl font-semibold text-primary-foreground shadow-inner" aria-label={`${book.book_name}封面`} role="img">{coverLetter(book)}</div>
                    <div className="min-w-0 flex-1"><div className="flex items-start justify-between gap-2"><h3 className="truncate font-semibold">{book.book_name}</h3><span className="shrink-0 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{statusLabel[book.status ?? ''] ?? book.status ?? '未知'}</span></div><p className="mt-1 truncate text-xs text-muted-foreground">{book.author || '作者未标注'} · {book.source_name || '本地内容'}</p><p className="mt-5 text-xs text-muted-foreground">{bookChapter(book)}<span className="mx-1.5">·</span>{formatDate(book.updated_at)}</p></div>
                  </div>
                  <div className="px-4 pb-4"><div className="mb-2 flex items-center justify-between text-xs"><span className="font-mono font-semibold text-primary">{percent}%</span><span className="text-muted-foreground">{book.total_chapters ? `${book.total_chapters} 章` : '章节统计中'}</span></div><div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${percent}%` }} /></div><div className="mt-4 flex gap-2"><Link to={`/novel/books/${book.id}/read/${book.progress?.chapter_id ?? 1}`} className="inline-flex h-9 flex-1 items-center justify-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90"><BookOpen className="h-3.5 w-3.5" aria-hidden="true" />继续阅读</Link><Link to={`/novel/books/${book.id}`} className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-input bg-card px-3 text-xs font-medium hover:bg-accent">详情<ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" /></Link></div></div>
                </Card>
              })}
            </div>
          </section>
        </>
      )}
    </ConsoleLayout>
  )
}
