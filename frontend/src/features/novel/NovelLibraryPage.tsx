import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowUpRight, BookOpen, Check, FileUp, Loader2, RefreshCw, Search, Sparkles, UploadCloud, Users, X } from 'lucide-react'

import {
  createNovelConversation,
  getNovelBook,
  getNovelCharacterDossier,
  importNovelFromSource,
  importNovelFromUrl,
  listNovelBooks,
  listNovelChapters,
  listNovelCharacters,
  previewNovel,
  searchNovelBooks,
  uploadNovel,
  type NovelBook,
  type NovelCharacterDossier,
  type NovelCharacterListItem,
  type NovelImportPreview,
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

const tierBadgeColors: Record<string, string> = {
  SSS: 'border-amber-500/50 bg-amber-500/10 text-amber-500',
  SS: 'border-purple-500/50 bg-purple-500/10 text-purple-400',
  S: 'border-sky-500/50 bg-sky-500/10 text-sky-400',
  A: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400',
  B: 'border-muted-foreground/50 bg-muted text-muted-foreground',
}

export function NovelLibraryPage() {
  const { bookId } = useParams<{ bookId?: string }>()
  const navigate = useNavigate()
  const uploadInput = useRef<HTMLInputElement>(null)
  const [books, setBooks] = useState<NovelBook[]>([])
  const [selectedBook, setSelectedBook] = useState<NovelBook | null>(null)
  const [chapters, setChapters] = useState<NovelChapter[]>([])
  const [characters, setCharacters] = useState<NovelCharacterListItem[]>([])
  const [loadingCharacters, setLoadingCharacters] = useState(false)
  const [bookTab, setBookTab] = useState<'characters' | 'chapters'>('characters')

  // 选中的人物档案对话框
  const [activeDossier, setActiveDossier] = useState<NovelCharacterDossier | null>(null)
  const [dossierModalOpen, setDossierModalOpen] = useState(false)
  const [loadingDossier, setLoadingDossier] = useState(false)
  const [dossierSubTab, setDossierSubTab] = useState<'relations' | 'events' | 'items' | 'excerpts' | 'profile'>('relations')

  const [keyword, setKeyword] = useState('')
  const [url, setUrl] = useState('')
  const [searchResults, setSearchResults] = useState<NovelSearchResult[]>([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [busyKey, setBusyKey] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pendingUpload, setPendingUpload] = useState<{ file: File; preview: NovelImportPreview } | null>(null)

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
      setCharacters([])
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

    async function loadCharacters() {
      setLoadingCharacters(true)
      try {
        const charRes = await listNovelCharacters(detailBookId)
        if (mounted) {
          setCharacters(charRes.data || [])
        }
      } catch {
        // dynamic fallback
      } finally {
        if (mounted) setLoadingCharacters(false)
      }
    }

    void loadDetail()
    void loadCharacters()

    return () => {
      mounted = false
    }
  }, [bookId])

  const currentBook = useMemo(() => {
    if (!bookId) return null
    return selectedBook ?? books.find((book) => String(book.id) === bookId) ?? null
  }, [bookId, books, selectedBook])

  const openCharacterDossier = async (characterName: string, forceRefresh = false) => {
    if (!currentBook) return
    setLoadingDossier(true)
    setDossierModalOpen(true)
    setDossierSubTab('relations')
    try {
      const res = await getNovelCharacterDossier(currentBook.id, characterName, forceRefresh)
      setActiveDossier(res.data)
    } catch {
      setError(`未能加载【${characterName}】的人物档案`)
    } finally {
      setLoadingDossier(false)
    }
  }

  const handleRefreshCharacters = async () => {
    if (!currentBook) return
    setLoadingCharacters(true)
    setNotice('正在调动 AI 阅读全书关键章节并提炼人物图谱，请稍候...')
    try {
      const res = await listNovelCharacters(currentBook.id, true)
      setCharacters(res.data || [])
      setNotice(`AI 已完成全书人物提炼并持久化保存，共提取 ${res.data?.length || 0} 位关键角色。`)
    } catch {
      setError('AI 提炼人物失败，请稍后重试。')
    } finally {
      setLoadingCharacters(false)
    }
  }

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
    setBusyKey(`preview:${file.name}`)
    setNotice('')
    setError('')
    try {
      const response = await previewNovel(file)
      setPendingUpload({ file, preview: response.data })
    } catch {
      setError(`无法预览 ${file.name}，支持 TXT、Markdown、HTML 和 EPUB。`)
      if (uploadInput.current) uploadInput.current.value = ''
    } finally {
      setBusyKey('')
    }
  }

  const confirmUpload = async () => {
    if (!pendingUpload) return
    setBusyKey(`upload:${pendingUpload.file.name}`)
    setNotice('')
    setError('')
    try {
      const response = await uploadNovel(pendingUpload.file)
      setPendingUpload(null)
      if (uploadInput.current) uploadInput.current.value = ''
      setNotice(`导入任务已创建：《${pendingUpload.preview.title || pendingUpload.file.name}》`)
      await loadBooks()
      if (response.data.book_id) {
        navigate(`/novel/books/${response.data.book_id}`)
      }
    } catch {
      setError(`上传 ${pendingUpload.file.name} 失败，请稍后重试。`)
    } finally {
      setBusyKey('')
    }
  }

  const importUrl = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!url.trim() || busyKey) return
    setBusyKey(`url:${url}`)
    setNotice('')
    setError('')
    try {
      const response = await importNovelFromUrl(url.trim())
      setUrl('')
      setNotice('链接解析任务已提交。')
      await loadBooks()
      if (response.data.book_id) {
        navigate(`/novel/books/${response.data.book_id}`)
      }
    } catch {
      setError('无法从该链接解析小说，请确认地址有效且书源已启用。')
    } finally {
      setBusyKey('')
    }
  }

  const openBookAssistant = async () => {
    if (!currentBook) return
    try {
      const conversation = await createNovelConversation({
        title: `关于《${currentBook.book_name}》的讨论`,
        bookId: Number(currentBook.id),
        entrypoint: 'book',
      })
      navigate(`/ai/workspace?conversation=${conversation.data.id}`)
    } catch {
      navigate(`/ai/workspace?book_id=${currentBook.id}`)
    }
  }

  return (
    <ConsoleLayout eyebrow="小说" title="小说工作台" description="全景人物关系图谱、原著事实考证、阅读理解与智能问答">
      {notice ? <div className="mb-5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">{notice}</div> : null}
      {error ? <div className="mb-5 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div> : null}

      {pendingUpload ? (
        <section aria-label="上传预览" className="mb-6 rounded-2xl border border-primary/40 bg-card p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-primary">导入预览</p>
              <h3 className="text-lg font-semibold">{pendingUpload.preview.title || pendingUpload.file.name}</h3>
              <p className="text-xs text-muted-foreground">{pendingUpload.preview.author || '作者未标注'} · 共 {pendingUpload.preview.chapters.length} 章 · {pendingUpload.preview.total_chars.toLocaleString()} 字</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setPendingUpload(null)}>取消</Button>
              <Button onClick={() => void confirmUpload()} disabled={Boolean(busyKey)}>
                {busyKey ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Check className="mr-2 h-4 w-4" aria-hidden="true" />}确认导入
              </Button>
            </div>
          </div>
          {pendingUpload.preview.warnings.length > 0 ? (
            <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-200">
              <p className="font-medium">分章提示：</p>
              <ul className="mt-1 list-inside list-disc space-y-1">
                {pendingUpload.preview.warnings.map((warning, index) => (
                  <li key={index}>{warning.message}</li>
                ))}
              </ul>
            </div>
          ) : <p className="mt-4 text-sm text-emerald-700 dark:text-emerald-300">未发现明显分章问题。</p>}
        </section>
      ) : null}

      {currentBook ? (
        <section className="space-y-6">
          <Card className="overflow-hidden border-0 bg-[linear-gradient(115deg,hsl(var(--primary)/.12),transparent_55%),hsl(var(--card))] shadow-sm">
            <div className="grid gap-6 p-6 md:grid-cols-[112px_minmax(0,1fr)_auto] md:items-center">
              <div className="grid aspect-[3/4] place-items-center rounded-lg bg-primary text-4xl font-semibold text-primary-foreground shadow-lg shadow-primary/20" aria-hidden="true">{coverLetter(currentBook)}</div>
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">Book dossier</p>
                  <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[11px] font-medium text-primary">已收录全本原著</span>
                </div>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight">{currentBook.book_name}</h2>
                <p className="mt-2 text-sm text-muted-foreground">{currentBook.author || '作者未标注'} · {currentBook.source_name || '本地校对全本'}</p>
                <p className="mt-4 max-w-2xl text-sm leading-7 text-muted-foreground">{currentBook.summary_global || '全书已完成事实索引构建。支持全人物关系解析、重大转折事件追溯与核心装备档案。'}</p>
              </div>
              <div className="flex flex-wrap gap-2 md:flex-col">
                <Button onClick={openBookAssistant}><Sparkles className="mr-2 h-4 w-4" aria-hidden="true" />问助手</Button>
                <Link to={`/novel/books/${currentBook.id}/read/${currentBook.progress?.chapter_id ?? chapters[0]?.id ?? 1}`} className="inline-flex h-10 items-center justify-center rounded-md border border-input bg-card px-4 text-sm font-medium hover:bg-accent">开始阅读</Link>
                <Button variant="ghost" size="sm" onClick={() => navigate('/novel/library')}>返回书架</Button>
              </div>
            </div>
          </Card>

          {/* 导航 Tab：登场人物 / 章节目录 */}
          <div className="flex items-center gap-2 border-b border-border pb-1">
            <button
              onClick={() => setBookTab('characters')}
              className={`inline-flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors ${
                bookTab === 'characters'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              <Users className="h-4 w-4" />
              <span>登场人物与图谱 ({characters.length})</span>
            </button>
            <button
              onClick={() => setBookTab('chapters')}
              className={`inline-flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors ${
                bookTab === 'chapters'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              <BookOpen className="h-4 w-4" />
              <span>章节索引 ({chapters.length})</span>
            </button>
          </div>

          {/* 登场人物列表专区 */}
          {bookTab === 'characters' ? (
            <section className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs text-muted-foreground">
                    由系统与 LLM 全量阅读原著正文抽取并持久化存储在数据库中。点击卡片可查看该角色的深度关系网络与一生事件。
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void handleRefreshCharacters()}
                    disabled={loadingCharacters}
                    className="h-8 gap-1.5 text-xs"
                  >
                    {loadingCharacters ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5" />
                    )}
                    <span>{loadingCharacters ? 'AI 正在深度提炼中...' : 'AI 重新提取人物'}</span>
                  </Button>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {characters.map((char) => {
                  const tierColor = tierBadgeColors[char.overall_tier] || tierBadgeColors.A
                  return (
                    <div
                      key={char.name}
                      onClick={() => void openCharacterDossier(char.name)}
                      className="group relative flex cursor-pointer flex-col justify-between rounded-xl border border-border bg-card p-5 transition-all hover:border-primary/60 hover:bg-accent/40 hover:shadow-md"
                    >
                      <div>
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-primary/10 font-serif text-lg font-bold text-primary shadow-inner">
                              {char.avatar_tag || char.name[0]}
                            </div>
                            <div>
                              <h3 className="text-base font-semibold group-hover:text-primary">{char.name}</h3>
                              <p className="text-xs text-muted-foreground">{char.role}</p>
                            </div>
                          </div>
                          <span className={`rounded-md border px-2 py-0.5 text-[11px] font-bold ${tierColor}`}>
                            {char.overall_tier}
                          </span>
                        </div>

                        {char.aliases?.length ? (
                          <div className="mt-3 flex flex-wrap gap-1">
                            {char.aliases.slice(0, 3).map((alias) => (
                              <span key={alias} className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                                {alias}
                              </span>
                            ))}
                          </div>
                        ) : null}

                        <p className="mt-3 line-clamp-3 text-xs leading-5 text-muted-foreground">
                          {char.summary}
                        </p>
                      </div>

                      <div className="mt-4 flex items-center justify-between border-t border-border/60 pt-3 text-[11px] text-muted-foreground">
                        <div className="flex gap-3">
                          <span>羁绊 <strong>{char.relationships_count}</strong></span>
                          <span>事件 <strong>{char.events_count}</strong></span>
                          <span>装备 <strong>{char.items_count}</strong></span>
                        </div>
                        <span className="inline-flex items-center gap-1 font-medium text-primary opacity-90 group-hover:opacity-100">
                          查看档案 <ArrowUpRight className="h-3 w-3" />
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>

              {!characters.length && !loadingCharacters ? (
                <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-14 text-center">
                  <Users className="h-10 w-10 text-muted-foreground/40" />
                  <h4 className="mt-3 text-base font-semibold">尚未提炼当前小说人物图谱</h4>
                  <p className="mt-1 max-w-md text-xs text-muted-foreground">
                    系统支持自动扫描全本真实章节，调用 AI 算法提取书中核心主要人物、别名与生平定位，并持久化到本地数据库。
                  </p>
                  <Button
                    onClick={() => void handleRefreshCharacters()}
                    className="mt-4 gap-2"
                  >
                    <Sparkles className="h-4 w-4" />
                    <span>立即让 AI 深度提炼全书人物</span>
                  </Button>
                </div>
              ) : null}
            </section>
          ) : (
            /* 章节索引列表 */
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
          )}

          {/* 人物全景深度档案模态框 (Dossier Modal) */}
          {dossierModalOpen ? (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
              <div className="relative flex max-h-[90vh] w-full max-w-4xl flex-col rounded-2xl border border-border bg-card shadow-2xl overflow-hidden">
                {/* 弹窗头部 */}
                <div className="flex items-center justify-between border-b border-border bg-muted/40 px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div className="grid h-10 w-10 place-items-center rounded-xl bg-primary text-base font-bold text-primary-foreground">
                      {activeDossier?.avatar_tag || activeDossier?.name?.[0] || '人'}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-lg font-bold tracking-tight">{activeDossier?.name || '人物档案'}</h2>
                        {activeDossier?.overall_tier ? (
                          <span className={`rounded px-2 py-0.5 text-xs font-bold ${tierBadgeColors[activeDossier.overall_tier] || tierBadgeColors.A}`}>
                            {activeDossier.overall_tier} 阶位
                          </span>
                        ) : null}
                      </div>
                      <p className="text-xs text-muted-foreground">{activeDossier?.role}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {activeDossier ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void openCharacterDossier(activeDossier.name, true)}
                        disabled={loadingDossier}
                        className="h-8 gap-1.5 text-xs"
                      >
                        {loadingDossier ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <RefreshCw className="h-3.5 w-3.5" />
                        )}
                        <span>{loadingDossier ? 'AI 正在解构...' : 'AI 重新深度解构'}</span>
                      </Button>
                    ) : null}
                    <Button variant="ghost" size="sm" onClick={() => setDossierModalOpen(false)}>
                      <X className="h-5 w-5" />
                    </Button>
                  </div>
                </div>

                {/* 弹窗子导航 Tabs */}
                <div className="flex items-center gap-1 border-b border-border bg-background/50 px-6">
                  <button
                    onClick={() => setDossierSubTab('relations')}
                    className={`border-b-2 px-3 py-2.5 text-xs font-semibold transition-colors ${
                      dossierSubTab === 'relations'
                        ? 'border-primary text-primary'
                        : 'border-transparent text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    人际关系网 ({activeDossier?.relationships?.length || 0})
                  </button>
                  <button
                    onClick={() => setDossierSubTab('events')}
                    className={`border-b-2 px-3 py-2.5 text-xs font-semibold transition-colors ${
                      dossierSubTab === 'events'
                        ? 'border-primary text-primary'
                        : 'border-transparent text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    关键转折事件 ({activeDossier?.events?.length || 0})
                  </button>
                  <button
                    onClick={() => setDossierSubTab('items')}
                    className={`border-b-2 px-3 py-2.5 text-xs font-semibold transition-colors ${
                      dossierSubTab === 'items'
                        ? 'border-primary text-primary'
                        : 'border-transparent text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    装备道具 ({activeDossier?.items?.length || 0})
                  </button>
                  <button
                    onClick={() => setDossierSubTab('excerpts')}
                    className={`border-b-2 px-3 py-2.5 text-xs font-semibold transition-colors ${
                      dossierSubTab === 'excerpts'
                        ? 'border-primary text-primary'
                        : 'border-transparent text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    原著依据 ({activeDossier?.canonical_excerpts?.length || 0})
                  </button>
                  <button
                    onClick={() => setDossierSubTab('profile')}
                    className={`border-b-2 px-3 py-2.5 text-xs font-semibold transition-colors ${
                      dossierSubTab === 'profile'
                        ? 'border-primary text-primary'
                        : 'border-transparent text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    身份与背景
                  </button>
                </div>

                {/* 弹窗内容滚动区 */}
                <div className="flex-1 overflow-y-auto p-6">
                  {loadingDossier ? (
                    <div className="flex h-64 items-center justify-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-5 w-5 animate-spin" />
                      正在检索该人物的原著全景档案...
                    </div>
                  ) : activeDossier ? (
                    <div className="space-y-5">
                      {/* 子 Tab 1: 人际关系网 */}
                      {dossierSubTab === 'relations' ? (
                        <div className="space-y-3">
                          <p className="text-xs text-muted-foreground">该角色与书中其他关键人物的纽带关系与剧情羁绊：</p>
                          <div className="grid gap-3 sm:grid-cols-2">
                            {activeDossier.relationships?.map((rel, idx) => (
                              <div key={idx} className="rounded-xl border border-border bg-muted/30 p-4">
                                <div className="flex items-center justify-between gap-2">
                                  <div className="flex items-center gap-2">
                                    <span className="font-bold text-foreground">{rel.target}</span>
                                    <span className="rounded bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">
                                      {rel.relation}
                                    </span>
                                  </div>
                                  {rel.affinity ? (
                                    <span className="text-xs font-mono font-medium text-amber-500">
                                      亲密 {rel.affinity}%
                                    </span>
                                  ) : null}
                                </div>
                                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                                  {rel.description}
                                </p>
                              </div>
                            ))}
                          </div>
                          {!activeDossier.relationships?.length ? (
                            <p className="py-8 text-center text-xs text-muted-foreground">暂无显著角色关系网络记录</p>
                          ) : null}
                        </div>
                      ) : null}

                      {/* 子 Tab 2: 关键转折事件 */}
                      {dossierSubTab === 'events' ? (
                        <div className="space-y-3">
                          <p className="text-xs text-muted-foreground">按原著时间线发生的核心重大转折与高光时刻：</p>
                          <div className="space-y-3">
                            {activeDossier.events?.map((ev, idx) => (
                              <div key={idx} className="relative rounded-xl border border-border bg-muted/20 p-4 pl-5">
                                <div className="absolute left-0 top-4 h-6 w-1 rounded-r bg-primary" />
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <h4 className="text-sm font-semibold">{ev.title}</h4>
                                  <span className="rounded bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                                    {ev.chapter}
                                  </span>
                                </div>
                                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                                  {ev.description}
                                </p>
                              </div>
                            ))}
                          </div>
                          {!activeDossier.events?.length ? (
                            <p className="py-8 text-center text-xs text-muted-foreground">暂无显著转折事件记录</p>
                          ) : null}
                        </div>
                      ) : null}

                      {/* 子 Tab 3: 装备与道具 */}
                      {dossierSubTab === 'items' ? (
                        <div className="space-y-3">
                          <p className="text-xs text-muted-foreground">该角色在正文中持有、获得或使用过的关键道具与装备：</p>
                          <div className="grid gap-3 sm:grid-cols-2">
                            {activeDossier.items?.map((item, idx) => (
                              <div key={idx} className="rounded-xl border border-border bg-muted/20 p-4">
                                <div className="flex items-center justify-between gap-2">
                                  <h4 className="font-semibold text-foreground">{item.name}</h4>
                                  <span className="rounded bg-sky-500/10 px-2 py-0.5 text-[10px] font-semibold text-sky-400">
                                    {item.action || '持有'}
                                  </span>
                                </div>
                                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                                  {item.desc}
                                </p>
                              </div>
                            ))}
                          </div>
                          {!activeDossier.items?.length ? (
                            <p className="py-8 text-center text-xs text-muted-foreground">暂无专属特殊道具装备记录</p>
                          ) : null}
                        </div>
                      ) : null}

                      {/* 子 Tab 4: 原著依据 */}
                      {dossierSubTab === 'excerpts' ? (
                        <div className="space-y-3">
                          <p className="text-xs text-muted-foreground">系统从本地原著全本章节中检索出的真实正文切片：</p>
                          <div className="space-y-3">
                            {activeDossier.canonical_excerpts?.map((ex, idx) => (
                              <div key={idx} className="rounded-xl border border-border bg-muted/30 p-4">
                                <span className="mb-2 inline-block rounded bg-primary/10 px-2 py-0.5 text-[11px] font-mono font-medium text-primary">
                                  {ex.chapter}
                                </span>
                                <p className="font-serif text-xs leading-relaxed text-foreground/90 whitespace-pre-wrap">
                                  ...{ex.text}...
                                </p>
                              </div>
                            ))}
                          </div>
                          {!activeDossier.canonical_excerpts?.length ? (
                            <p className="py-8 text-center text-xs text-muted-foreground">暂无正文摘录</p>
                          ) : null}
                        </div>
                      ) : null}

                      {/* 子 Tab 5: 身份与背景 */}
                      {dossierSubTab === 'profile' ? (
                        <div className="space-y-4">
                          <div className="rounded-xl border border-border bg-muted/20 p-4">
                            <h4 className="text-xs font-semibold uppercase tracking-wider text-primary">全书生平简介</h4>
                            <p className="mt-2 text-xs leading-relaxed text-foreground/90">{activeDossier.summary}</p>
                          </div>
                          <div className="grid gap-3 sm:grid-cols-2">
                            <div className="rounded-xl border border-border bg-muted/20 p-4">
                              <span className="text-[11px] text-muted-foreground">身份背景与演进</span>
                              <p className="mt-1 text-xs font-medium">{activeDossier.personal_info?.identity || activeDossier.role}</p>
                            </div>
                            <div className="rounded-xl border border-border bg-muted/20 p-4">
                              <span className="text-[11px] text-muted-foreground">性格与主导心态</span>
                              <p className="mt-1 text-xs font-medium">{activeDossier.personal_info?.mentality || '性格坚毅，具有极强目的性'}</p>
                            </div>
                            <div className="rounded-xl border border-border bg-muted/20 p-4">
                              <span className="text-[11px] text-muted-foreground">阵营归属</span>
                              <p className="mt-1 text-xs font-medium">{activeDossier.alignment || '核心阵营'}</p>
                            </div>
                            <div className="rounded-xl border border-border bg-muted/20 p-4">
                              <span className="text-[11px] text-muted-foreground">生存状态</span>
                              <p className="mt-1 text-xs font-medium">{activeDossier.personal_info?.status || '活跃中'}</p>
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}
        </section>
      ) : (
        <>
          <section className="grid gap-4 rounded-2xl border border-border bg-[linear-gradient(120deg,hsl(var(--primary)/.13),transparent_42%),hsl(var(--card))] p-5 shadow-sm md:grid-cols-[1fr_auto] md:items-end md:p-7">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Reading room / 01</p>
              <h2 className="mt-3 max-w-xl text-3xl font-semibold tracking-tight md:text-4xl">把故事放回它该在的地方。</h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground">每一本书都有自己的阅读进度、原著全量证据和全景人物关系图谱。你可以从任何入口回来，接着读，也接着问。</p>
            </div>
            <div className="flex items-center gap-5 border-t border-border/70 pt-4 md:border-l md:border-t-0 md:pl-6 md:pt-0">
              <div><p className="font-mono text-2xl font-semibold">{books.length}</p><p className="text-xs text-muted-foreground">书架藏书</p></div>
              <div><p className="font-mono text-2xl font-semibold">{books.filter((book) => book.status === 'ready').length}</p><p className="text-xs text-muted-foreground">全本已就绪</p></div>
              <div><p className="font-mono text-2xl font-semibold">{books.reduce((sum, b) => sum + (b.character_count || 0), 0)}</p><p className="text-xs text-muted-foreground">图谱人物</p></div>
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

          {searchResults.length > 0 ? (
            <section aria-label="搜索结果" className="rounded-xl border border-border bg-card p-4">
              <div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-semibold">书源搜索结果</h3><span className="text-xs text-muted-foreground">{searchResults.length} 条可用</span></div>
              <div className="grid gap-2">
                {searchResults.map((result) => {
                  const key = `${result.sourceId}:${result.bookUrl}`
                  return (
                    <div key={key} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/80 bg-background/50 px-4 py-3 text-sm">
                      <div><p className="font-medium">{result.name}</p><p className="text-xs text-muted-foreground">{result.author || '未知作者'} · {result.sourceName || `书源 #${result.sourceId}`}</p></div>
                      <Button size="sm" onClick={() => void addFromSource(result)} disabled={busyKey === key}>{busyKey === key ? <Loader2 className="h-4 w-4 animate-spin" aria-label="正在导入" /> : '加入书架'}</Button>
                    </div>
                  )
                })}
              </div>
            </section>
          ) : null}

          <section aria-label="书籍列表" className="space-y-4">
            <div className="flex items-center justify-between"><h3 className="font-serif text-lg font-semibold tracking-tight">全部藏书</h3><span className="text-xs text-muted-foreground">{loading ? '正在同步…' : `${books.length} 本`}</span></div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {books.map((book) => {
                const isReady = book.status === 'ready'
                const isAnalyzing = book.status === 'summarizing' || book.status === 'ingesting'
                const charCount = book.character_count ?? 0
                const readPercent = Math.round(Math.max(0, Math.min(1, Number(book.progress?.percent ?? 0))) * 100)
                const ingestPercent = Math.round(Math.max(0, Math.min(1, Number(book.ingest_progress ?? 1))) * 100)

                return (
                  <Card key={book.id} className="flex flex-col justify-between overflow-hidden border border-border bg-card transition hover:border-primary/50 hover:shadow-md">
                    <div className="p-5">
                      <div className="flex items-start gap-4">
                        <div className="grid h-16 w-12 shrink-0 place-items-center rounded bg-primary/10 font-serif text-xl font-bold text-primary">{coverLetter(book)}</div>
                        <div className="min-w-0 flex-1">
                          <h4 className="truncate font-semibold tracking-tight"><Link to={`/novel/books/${book.id}`} className="hover:text-primary">{book.book_name}</Link></h4>
                          <p className="mt-1 truncate text-xs text-muted-foreground">{book.author || '作者未标注'} · {book.source_name || '本地内容'}</p>
                          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                            {isReady ? (
                              <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                                全本可读
                              </span>
                            ) : isAnalyzing ? (
                              <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
                                <Loader2 className="h-3 w-3 animate-spin" />
                                正在解析入库 · {ingestPercent}%
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                                {statusLabel[book.status ?? ''] || book.status}
                              </span>
                            )}
                            {charCount > 0 ? (
                              <span className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                                <Users className="h-3 w-3" />
                                {charCount} 位人物图谱
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="border-t border-border bg-muted/20 px-5 py-3.5">
                      {isReady || book.progress ? (
                        <>
                          <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
                            <span>阅读进度：{book.progress?.chapter_title || (book.progress?.chapter_id ? `第 ${book.progress.chapter_id} 章` : '尚未开始阅读')}</span>
                            <span className="font-mono"><span>{readPercent}%</span> · 共 {book.total_chapters ?? 0} 章</span>
                          </div>
                          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                            <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${readPercent}%` }} />
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
                            <span>系统解析进度</span>
                            <span className="font-mono"><span>{ingestPercent}%</span> · 共 {book.total_chapters ?? 0} 章</span>
                          </div>
                          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                            <div className="h-full rounded-full bg-amber-500 transition-[width] duration-500" style={{ width: `${ingestPercent}%` }} />
                          </div>
                        </>
                      )}
                      <div className="mt-4 flex gap-2">
                        <Link to={`/novel/books/${book.id}/read/${book.progress?.chapter_id ?? 1}`} className="inline-flex h-9 flex-1 items-center justify-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90">
                          <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
                          {book.progress?.chapter_id ? '继续阅读' : '开始阅读'}
                        </Link>
                        <Link to={`/novel/books/${book.id}`} className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-input bg-card px-3 text-xs font-medium hover:bg-accent">
                          详情与图谱<ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
                        </Link>
                      </div>
                    </div>
                  </Card>
                )
              })}
            </div>
          </section>
        </>
      )}
    </ConsoleLayout>
  )
}
