import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ChevronLeft, ChevronRight, Minus, Moon, PanelRight, Plus, Send, Settings2, Sparkles, Sun, Trees } from 'lucide-react'

import {
  createNovelConversation,
  getNovelBook,
  getNovelChapter,
  getNovelProgress,
  listNovelChapters,
  saveNovelProgress,
  sendNovelMessage,
  type NovelBook,
  type NovelChapter,
  type NovelConversationMessage,
  type NovelReadingProgress,
} from '@/api/modules/novel'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

type ReaderTheme = 'paper' | 'night' | 'green'
type ContentWidth = 'compact' | 'comfortable'

const themeOptions: Array<{ value: ReaderTheme; label: string; icon: typeof Sun }> = [
  { value: 'paper', label: '纸张', icon: Sun },
  { value: 'night', label: '夜读', icon: Moon },
  { value: 'green', label: '青绿', icon: Trees },
]

function numericId(value?: string) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function clampFontSize(value: number) {
  return Math.max(14, Math.min(30, value))
}

function toParagraphs(text: string) {
  return text.split(/\n{2,}|\n/).map((line) => line.trim()).filter(Boolean)
}

export function NovelReaderPage() {
  const { bookId: rawBookId, chapterId: rawChapterId } = useParams<{ bookId: string; chapterId: string }>()
  const navigate = useNavigate()
  const bookId = numericId(rawBookId)
  const chapterId = numericId(rawChapterId)
  const [book, setBook] = useState<NovelBook | null>(null)
  const [chapters, setChapters] = useState<NovelChapter[]>([])
  const [chapter, setChapter] = useState<NovelChapter | null>(null)
  const [progress, setProgress] = useState<NovelReadingProgress | null>(null)
  const [theme, setTheme] = useState<ReaderTheme>('paper')
  const [background, setBackground] = useState('')
  const [fontSize, setFontSize] = useState(18)
  const [lineHeight, setLineHeight] = useState(1.9)
  const [contentWidth, setContentWidth] = useState<ContentWidth>('comfortable')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [assistantLoading, setAssistantLoading] = useState(false)
  const [assistantSending, setAssistantSending] = useState(false)
  const [assistantId, setAssistantId] = useState<string | null>(null)
  const [assistantTitle, setAssistantTitle] = useState('阅读助手')
  const [assistantInput, setAssistantInput] = useState('')
  const [assistantMessages, setAssistantMessages] = useState<NovelConversationMessage[]>([])

  const currentIndex = useMemo(() => chapters.findIndex((item) => item.id === chapterId), [chapters, chapterId])
  const previousChapter = currentIndex > 0 ? chapters[currentIndex - 1] : undefined
  const nextChapter = currentIndex >= 0 && currentIndex < chapters.length - 1 ? chapters[currentIndex + 1] : undefined
  const paragraphs = useMemo(() => toParagraphs(chapter?.raw_text || '这一章还没有正文，内容摄入完成后会出现在这里。'), [chapter?.raw_text])
  const readerStyle = {
    backgroundImage: background ? `url(${background})` : undefined,
    fontSize: `${fontSize}px`,
    lineHeight,
  }

  useEffect(() => {
    let mounted = true
    async function loadReader() {
      setLoading(true)
      try {
        const [bookResponse, chaptersResponse, chapterResponse, progressResponse] = await Promise.all([
          getNovelBook(bookId),
          listNovelChapters(bookId),
          getNovelChapter(bookId, chapterId),
          getNovelProgress(bookId),
        ])
        if (!mounted) return
        setBook(bookResponse.data)
        setChapters(chaptersResponse.data)
        setChapter(chapterResponse.data)
        setProgress(progressResponse.data)
        if (progressResponse.data?.theme === 'night' || progressResponse.data?.theme === 'green' || progressResponse.data?.theme === 'paper') setTheme(progressResponse.data.theme)
        if (progressResponse.data?.background) setBackground(progressResponse.data.background)
        if (progressResponse.data?.font_size) setFontSize(progressResponse.data.font_size)
        setError('')
      } catch {
        if (mounted) setError('章节加载失败，请返回书架稍后重试。')
      } finally {
        if (mounted) setLoading(false)
      }
    }
    void loadReader()
    return () => {
      mounted = false
    }
  }, [bookId, chapterId])

  const persistProgress = (next: { theme?: ReaderTheme; fontSize?: number; background?: string; lineHeight?: number; contentWidth?: ContentWidth } = {}) => {
    if (!bookId || !chapterId) return
    const preferences = {
      theme: next.theme ?? theme,
      background: next.background ?? background,
      fontSize: next.fontSize ?? fontSize,
      lineHeight: next.lineHeight ?? lineHeight,
      contentWidth: next.contentWidth ?? contentWidth,
    }
    void saveNovelProgress(bookId, {
      chapterId,
      offsetChars: progress?.offset_chars ?? 0,
      percent: progress?.percent ?? 0,
      preferences,
    })
  }

  const changeTheme = (value: ReaderTheme) => {
    setTheme(value)
    persistProgress({ theme: value })
  }

  const changeFontSize = (delta: number) => {
    const next = clampFontSize(fontSize + delta)
    setFontSize(next)
    persistProgress({ fontSize: next })
  }

  const changeLineHeight = (delta: number) => {
    const next = Math.max(1.5, Math.min(2.4, Number((lineHeight + delta).toFixed(1))))
    setLineHeight(next)
    persistProgress({ lineHeight: next })
  }

  const changeBackground = (value: string) => {
    setBackground(value)
    persistProgress({ background: value })
  }

  const changeWidth = (value: ContentWidth) => {
    setContentWidth(value)
    persistProgress({ contentWidth: value })
  }

  const openAssistant = async () => {
    setAssistantOpen(true)
    if (assistantId || assistantLoading) return
    setAssistantLoading(true)
    try {
      const response = await createNovelConversation({
        title: book ? `《${book.book_name}》阅读助手` : '阅读助手',
        bookId,
        chapterId,
        entrypoint: 'reader',
      })
      setAssistantId(response.data.id)
      setAssistantTitle(response.data.title || '阅读助手')
      setAssistantMessages(response.data.messages ?? [])
    } catch {
      setError('阅读助手暂时无法打开。')
    } finally {
      setAssistantLoading(false)
    }
  }

  const sendAssistantMessage = async (event: FormEvent) => {
    event.preventDefault()
    const content = assistantInput.trim()
    if (!content || !assistantId || assistantSending) return
    setAssistantSending(true)
    setAssistantInput('')
    try {
      const response = await sendNovelMessage(assistantId, {
        content,
        entrypoint: 'reader',
        bookId,
        chapterId,
        mode: 'chat',
        stream: false,
      })
      const userMessage: NovelConversationMessage = {
        id: `local-user-${Date.now()}`,
        role: 'user',
        mode: 'chat',
        content,
        created_at: new Date().toISOString(),
      }
      setAssistantMessages((current) => [...current, userMessage, response.data])
    } catch {
      setError('助手回复失败，问题已保留在输入框之外，请稍后重试。')
    } finally {
      setAssistantSending(false)
    }
  }

  const moveChapter = (next?: NovelChapter) => {
    if (!next) return
    persistProgress()
    navigate(`/novel/books/${bookId}/read/${next.id}`)
  }

  return (
    <ConsoleLayout
      eyebrow="NOVEL / READER"
      title={book?.book_name || '阅读器'}
      description={chapter ? `${chapter.canonical_full || `第 ${chapter.chapter_num ?? ''} 章`} · ${chapter.chapter_title}` : '正在加载章节内容…'}
      actions={<div className="flex flex-wrap items-center gap-2"><Link to="/novel/library" className="inline-flex h-10 items-center gap-2 rounded-md border border-input bg-card px-3 text-sm font-medium hover:bg-accent"><ArrowLeft className="h-4 w-4" aria-hidden="true" />书架</Link><Button onClick={() => void openAssistant()}><Sparkles className="mr-2 h-4 w-4" aria-hidden="true" />问助手</Button></div>}
    >
      {error ? <p role="alert" className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</p> : null}
      {loading ? <div className="grid min-h-[560px] place-items-center rounded-2xl border border-border bg-card text-sm text-muted-foreground">正在翻开这一章…</div> : null}
      {!loading ? <div className="relative">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
          <div className="flex items-center gap-2"><Button variant="ghost" size="icon" aria-label="上一章" title="上一章" disabled={!previousChapter} onClick={() => moveChapter(previousChapter)}><ChevronLeft className="h-4 w-4" /></Button><label className="sr-only" htmlFor="reader-chapter">选择章节</label><select id="reader-chapter" aria-label="选择章节" value={chapterId} onChange={(event) => moveChapter(chapters.find((item) => item.id === Number(event.target.value)))} className="h-9 max-w-[240px] rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring">{chapters.map((item) => <option key={item.id} value={item.id}>{item.canonical_full || `第${item.chapter_num ?? ''}章`} {item.chapter_title}</option>)}</select><Button variant="ghost" size="icon" aria-label="下一章" title="下一章" disabled={!nextChapter} onClick={() => moveChapter(nextChapter)}><ChevronRight className="h-4 w-4" /></Button></div>
          <div className="flex flex-wrap items-center gap-2"><div className="flex items-center rounded-md border border-border bg-muted/30 p-0.5" aria-label="阅读主题">{themeOptions.map(({ value, label, icon: Icon }) => <button key={value} type="button" aria-label={label} aria-pressed={theme === value} onClick={() => changeTheme(value)} className={`grid h-8 w-8 place-items-center rounded text-muted-foreground transition-colors hover:bg-accent ${theme === value ? 'bg-card text-primary shadow-sm' : ''}`}><Icon className="h-4 w-4" aria-hidden="true" /></button>)}</div><div className="flex items-center gap-1 rounded-md border border-border bg-muted/30 p-0.5"><Button variant="ghost" size="icon" aria-label="减小字号" title="减小字号" onClick={() => changeFontSize(-1)}><Minus className="h-3.5 w-3.5" /></Button><span className="w-10 text-center font-mono text-xs" aria-live="polite">{fontSize}px</span><Button variant="ghost" size="icon" aria-label="增大字号" title="增大字号" onClick={() => changeFontSize(1)}><Plus className="h-3.5 w-3.5" /></Button></div><details className="relative"><summary className="flex h-9 cursor-pointer list-none items-center gap-1 rounded-md border border-input bg-card px-3 text-xs font-medium hover:bg-accent"><Settings2 className="h-3.5 w-3.5" aria-hidden="true" />排版</summary><div className="absolute right-0 z-10 mt-2 w-64 space-y-4 rounded-lg border border-border bg-popover p-4 text-sm shadow-xl"><label className="block">行距 <input aria-label="行距" type="range" min="1.5" max="2.4" step="0.1" value={lineHeight} onChange={(event) => { const next = Number(event.target.value); setLineHeight(next); persistProgress({ lineHeight: next }) }} className="mt-2 w-full accent-primary" /></label><fieldset><legend className="mb-2 text-xs text-muted-foreground">正文宽度</legend><div className="flex gap-2"><button type="button" className={`rounded border px-2 py-1 text-xs ${contentWidth === 'compact' ? 'border-primary text-primary' : 'border-border'}`} onClick={() => changeWidth('compact')}>窄版</button><button type="button" className={`rounded border px-2 py-1 text-xs ${contentWidth === 'comfortable' ? 'border-primary text-primary' : 'border-border'}`} onClick={() => changeWidth('comfortable')}>舒展</button></div></fieldset><label className="block">自定义背景<Input aria-label="自定义背景" value={background} onChange={(event) => changeBackground(event.target.value)} placeholder="输入图片地址…" className="mt-2 h-9 text-xs" /></label></div></details></div>
        </div>

        <article data-testid="reader-surface" data-reader-theme={theme} className={`overflow-hidden rounded-2xl border shadow-sm ${theme === 'night' ? 'border-slate-700 bg-slate-950 text-slate-200' : theme === 'green' ? 'border-emerald-900/20 bg-[#edf4ed] text-[#1f3629] dark:border-emerald-300/20 dark:bg-[#17251d] dark:text-emerald-50' : 'border-[#ded6c8] bg-[#fbf7ef] text-[#332e28] dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100'}`} style={{ backgroundImage: background ? `linear-gradient(rgba(255,255,255,.68),rgba(255,255,255,.68)),url(${background})` : undefined }}>
          <div className="mx-auto max-w-3xl px-6 py-12 sm:px-12 sm:py-16 lg:px-20"><header className="mb-10 border-b border-current/10 pb-8"><p className="font-mono text-xs uppercase tracking-[0.24em] opacity-60">{chapter?.canonical_full || 'Chapter'}</p><h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">{chapter?.chapter_title || '未命名章节'}</h1><p className="mt-3 text-xs opacity-60">{chapter?.word_count ? `${chapter.word_count.toLocaleString()} 字` : '正文统计中'} · 这是你的私有阅读空间</p></header><div data-testid="reader-content" className={`${contentWidth === 'compact' ? 'max-w-[38rem]' : 'max-w-[48rem]'} space-y-6 font-serif tracking-[0.015em]`} style={readerStyle}>{paragraphs.map((paragraph, index) => <p key={`${index}-${paragraph.slice(0, 12)}`} className="text-pretty">{paragraph}</p>)}</div><footer className="mt-14 flex items-center justify-between border-t border-current/10 pt-5 text-xs opacity-60"><span>Legado Hub Reader</span><span>{currentIndex >= 0 ? `${currentIndex + 1} / ${chapters.length}` : ''}</span></footer></div>
        </article>
      </div> : null}

      {assistantOpen ? <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-border bg-card shadow-2xl" aria-label="阅读助手" role="dialog" aria-modal="true"><header className="flex items-center justify-between border-b border-border px-5 py-4"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Reader context</p><h2 className="mt-1 font-semibold">{assistantTitle}</h2><p className="mt-1 text-xs text-muted-foreground">当前书籍 · 第 {chapter?.chapter_num ?? ''} 章</p></div><Button variant="ghost" size="icon" aria-label="关闭阅读助手" onClick={() => setAssistantOpen(false)}><PanelRight className="h-4 w-4" /></Button></header><div className="flex-1 space-y-4 overflow-y-auto bg-muted/20 p-5">{assistantLoading ? <p className="text-sm text-muted-foreground">正在建立章节上下文…</p> : null}{!assistantLoading && !assistantMessages.length ? <div className="rounded-lg border border-dashed border-border bg-card p-4 text-sm leading-6 text-muted-foreground">我已经把《{book?.book_name || '这本书'}》的当前章节和阅读位置带进来了。你可以问人物、证据、伏笔或这一段的情绪变化。</div> : null}{assistantMessages.map((message) => <article key={message.id} className={`rounded-lg border px-4 py-3 text-sm leading-6 ${message.role === 'user' ? 'ml-8 border-primary bg-primary text-primary-foreground' : 'mr-4 border-border bg-card'}`}><p className="mb-1 text-[11px] font-semibold uppercase tracking-wider opacity-60">{message.role === 'user' ? '你' : 'Agent'}</p><p className="whitespace-pre-wrap">{message.content}</p></article>)}</div><form onSubmit={sendAssistantMessage} className="border-t border-border bg-card p-4"><div className="flex gap-2"><Input aria-label="助手问题" value={assistantInput} onChange={(event) => setAssistantInput(event.target.value)} placeholder="问当前章节…" disabled={!assistantId || assistantSending} /><Button type="submit" size="icon" aria-label="发送问题" disabled={!assistantId || assistantSending || !assistantInput.trim()}><Send className="h-4 w-4" /></Button></div></form></aside> : null}
    </ConsoleLayout>
  )
}
