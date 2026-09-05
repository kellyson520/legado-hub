import { useEffect, useMemo, useRef, useState } from 'react'

import {
  createAIConversation,
  decideAIConversationAuthorization,
  getAIConversation,
  listAIAuthorizationGrants,
  listAIConversationAuthorizations,
  listAIConversations,
  revokeAIAuthorizationGrant,
  sendAIConversationMessage,
  type AIConversation,
  type AIConversationAuthorizationGrant,
  type AIConversationAuthorizationRequest,
  type AIConversationMessage,
  type AIConversationSummary,
  type AIWorkspaceMode,
} from '@/api/modules/ai'
import { listNovelBooks, listNovelModels, type NovelBook, type NovelModelOption } from '@/api/modules/novel'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { StatusMessage } from '@/components/data/StatusMessage'
import { MarkdownMessage } from '@/components/ai/MarkdownMessage'
import { ToolResultRenderer } from '@/components/ai/ToolResultRenderer'
import { FormActions } from '@/components/form/FormActions'
import { FormField } from '@/components/form/FormField'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { Button } from '@/components/ui/button'
import { useServerPagination } from '@/hooks/useServerPagination'
import { formatFullTime, formatRelativeTime } from '@/lib/time'

const modes: Array<{ value: AIWorkspaceMode; label: string; description: string }> = [
  { value: 'chat', label: '通用问答', description: '围绕阅读、书源和小说提出问题' },
  { value: 'character', label: '人物介绍', description: '梳理人物关系、动机与性格' },
  { value: 'storyline', label: '剧情解析', description: '分析冲突、转折与时间线' },
  { value: 'world', label: '世界观', description: '提炼设定、势力和运行规则' },
]

const toolOptions = [
  { name: 'list_visible_sources', label: '列出可见书源', detail: '仅返回你有权查看的书源摘要' },
  { name: 'get_source_rule_summary', label: '读取书源规则摘要', detail: '需填写书源版本 ID，仅读取规则概览' },
  { name: 'list_ai_analysis_results', label: '查看我的分析结果', detail: '仅读取当前账户的 AI 任务结果' },
] as const

const authorizationToolLabels: Record<string, { zh: string; en: string }> = {
  'source.search': { zh: '搜索已启用书源', en: 'Search enabled sources' },
  'toc.get': { zh: '读取作品目录', en: 'Read the table of contents' },
  'chapter.fetch': { zh: '读取章节原文', en: 'Read chapter text' },
}

const modeLabel: Record<AIWorkspaceMode, string> = Object.fromEntries(modes.map((mode) => [mode.value, mode.label])) as Record<AIWorkspaceMode, string>

function MessageTime({ value, locale, compact = false }: { value: string; locale: 'zh-CN' | 'en-US'; compact?: boolean }) {
  const full = formatFullTime(value, locale)
  const relative = formatRelativeTime(value, locale)
  return (
    <time dateTime={value} title={full} className={compact ? 'text-right' : 'text-right'}>
      <span className="block">{relative}</span>
      <span className="block text-[10px] opacity-70">{full}</span>
    </time>
  )
}

export function AIWorkspacePage() {
  const { locale, t } = useLanguage()
  const pagination = useServerPagination<AIConversationSummary>({
    pageSize: 20,
    load: listAIConversations,
  })
  const { rows: conversations, loading: loadingConversations } = pagination
  const [books, setBooks] = useState<NovelBook[]>([])
  const [models, setModels] = useState<NovelModelOption[]>([])
  const [selectedBookId, setSelectedBookId] = useState('')
  const [selectedModel, setSelectedModel] = useState('')
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [conversation, setConversation] = useState<AIConversation | null>(null)
  const [mode, setMode] = useState<AIWorkspaceMode>('chat')
  const [content, setContent] = useState('')
  const [enabledTools, setEnabledTools] = useState<string[]>([])
  const [sourceVersionId, setSourceVersionId] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [pendingAuthorizations, setPendingAuthorizations] = useState<AIConversationAuthorizationRequest[]>([])
  const [authorizationGrants, setAuthorizationGrants] = useState<AIConversationAuthorizationGrant[]>([])
  const [authorizationBusy, setAuthorizationBusy] = useState<string | null>(null)
  const loadGeneration = useRef(0)

  const toolRequests = useMemo<Array<{ name: string; arguments: Record<string, string> }>>(() => enabledTools.map((name) => ({
    name,
    arguments: name === 'get_source_rule_summary' ? { source_version_id: sourceVersionId.trim() } : {} as Record<string, string>,
  })), [enabledTools, sourceVersionId])
  const requiresSourceVersion = enabledTools.includes('get_source_rule_summary')
  const canSend = Boolean(activeConversationId && content.trim() && !sending && (!requiresSourceVersion || sourceVersionId.trim()))

  const loadConversation = async (conversationId: string) => {
    const generation = ++loadGeneration.current
    const response = await getAIConversation(conversationId)
    if (generation !== loadGeneration.current) return
    setActiveConversationId(conversationId)
    if (response.data.book_id != null) setSelectedBookId(String(response.data.book_id))
    if (response.data.model_ref) setSelectedModel(response.data.model_ref)
    const hydratePendingCards = (pending: AIConversationAuthorizationRequest[]) => {
      if (generation !== loadGeneration.current) return
      const existingRequestIds = new Set(
        response.data.messages
          .map((message) => message.authorization_request?.id)
          .filter((id): id is string => Boolean(id)),
      )
      const synthetic = pending
        .filter((request) => !existingRequestIds.has(request.id))
        .map((request) => ({
          id: `authorization-${request.id}`,
          role: 'assistant' as const,
          mode: 'chat' as AIWorkspaceMode,
          content: '需要你的授权才能读取书源原文。',
          status: 'authorization_required' as const,
          tool_calls: [],
          authorization_request: request,
          created_at: new Date().toISOString(),
        }))
      setConversation({ ...response.data, messages: [...response.data.messages, ...synthetic] })
    }
    try {
      const [pending, grants] = await Promise.all([
        listAIConversationAuthorizations(conversationId),
        listAIAuthorizationGrants(conversationId),
      ])
      if (generation !== loadGeneration.current) return
      setPendingAuthorizations(pending.data)
      setAuthorizationGrants(grants.data)
      hydratePendingCards(pending.data)
    } catch {
      if (generation !== loadGeneration.current) return
      const pending = response.data.authorization_requests ?? []
      setPendingAuthorizations(pending)
      hydratePendingCards(pending)
    }
  }

  const loadNovelContext = async () => {
    try {
      const [booksResponse, modelsResponse] = await Promise.all([listNovelBooks(), listNovelModels()])
      setBooks(booksResponse.data)
      setModels(modelsResponse.data.novel_chat ?? [])
    } catch {
      // Novel context is optional; the existing AI workspace remains usable.
    }
  }

  useEffect(() => {
    if (!activeConversationId && conversations[0]) {
      void loadConversation(conversations[0].id)
    }
    if (!loadingConversations && conversations.length === 0) {
      loadGeneration.current += 1
      setActiveConversationId(null)
      setConversation(null)
    }
  }, [activeConversationId, conversations, loadingConversations])

  useEffect(() => {
    void loadNovelContext()
  }, [])

  const createConversation = async () => {
    if (sending) return
    loadGeneration.current += 1
    setSending(true)
    try {
      const response = await createAIConversation({
        title: t('新的 AI 对话'),
        ...(selectedBookId ? { book_id: Number(selectedBookId) } : {}),
        ...(selectedModel ? { model: selectedModel } : {}),
        entrypoint: 'workspace',
      })
      const next = response.data
      setConversation({ ...next, messages: [] })
      setActiveConversationId(next.id)
      setPendingAuthorizations([])
      setAuthorizationGrants([])
      pagination.reload()
      setContent('')
      setError('')
    } catch {
      setError('创建 AI 对话失败，请稍后重试。')
    } finally {
      setSending(false)
    }
  }

  const switchConversation = async (conversationId: string) => {
    if (conversationId === activeConversationId || sending) return
    try {
      await loadConversation(conversationId)
      setError('')
    } catch {
      setError('加载此对话失败，请稍后重试。')
    }
  }

  const send = async (
    outgoingContent = content.trim(),
    outgoingMode = mode,
    outgoingTools = toolRequests
  ) => {
    if (!activeConversationId || !outgoingContent || sending) return
    setSending(true)
    setError('')
    const createdAt = new Date().toISOString()
    const optimisticUser: AIConversationMessage = {
      id: `pending-${Date.now()}`,
      role: 'user',
      mode: outgoingMode,
      content: outgoingContent,
      status: 'succeeded',
      tool_calls: [],
      created_at: createdAt,
    }
    setConversation((current) => current ? { ...current, messages: [...current.messages, optimisticUser] } : current)
    setContent('')
    try {
      const response = await sendAIConversationMessage(activeConversationId, {
        content: outgoingContent,
        mode: outgoingMode,
        tool_requests: outgoingTools,
        source_version_id: outgoingTools.some((tool) => tool.name === 'get_source_rule_summary') ? sourceVersionId.trim() : undefined,
        entrypoint: 'workspace',
        ...(selectedBookId ? { book_id: Number(selectedBookId) } : {}),
        ...(selectedModel ? { model: selectedModel } : {}),
      })
      setConversation((current) => current ? { ...current, messages: [...current.messages, response.data] } : current)
    } catch {
      const failed: AIConversationMessage = {
        id: `failed-${Date.now()}`,
        role: 'assistant',
        mode: outgoingMode,
        content: '服务调用失败，请稍后重试。',
        status: 'failed',
        tool_calls: [],
        created_at: new Date().toISOString(),
      }
      setConversation((current) => current ? { ...current, messages: [...current.messages, failed] } : current)
      setError('AI 服务暂时不可用，已保留你的问题，可点击失败消息上的“重试”。')
    } finally {
      setSending(false)
    }
  }

  const retryMessage = (messageIndex: number) => {
    const messages = conversation?.messages ?? []
    const user = messages.slice(0, messageIndex).reverse().find((message) => message.role === 'user')
    if (!user) return
    void send(user.content, user.mode)
  }

  const decideAuthorization = async (request: AIConversationAuthorizationRequest, decision: 'once' | 'conversation' | 'remember' | 'deny') => {
    if (!activeConversationId || authorizationBusy) return
    setAuthorizationBusy(request.id)
    setError('')
    try {
      const response = await decideAIConversationAuthorization(activeConversationId, request.id, { decision })
      const resolved = response.data.authorization
      const terminal = ['denied', 'consumed', 'failed', 'expired'].includes(resolved.status)
      const resolvedContent = resolved.status === 'denied'
        ? t('ai.authorization.deniedMessage')
        : resolved.status === 'consumed'
          ? t('ai.authorization.approvedMessage')
          : resolved.status === 'expired'
            ? t('ai.authorization.expiredMessage')
            : t('ai.authorization.failedMessage')
      setPendingAuthorizations((current) => current.filter((item) => item.id !== request.id))
      setConversation((current) => {
        if (!current) return current
        const messages = current.messages.map((message) => {
          if (message.authorization_request?.id !== request.id) return message
          if (!terminal) {
            return { ...message, authorization_request: resolved }
          }
          return {
            ...message,
            content: resolvedContent,
            status: resolved.status === 'denied' ? 'denied' as const : resolved.status === 'consumed' ? 'succeeded' as const : 'failed' as const,
            authorization_request: resolved,
          }
        })
        const resumed = response.data.message
        if (resumed && !messages.some((message) => message.id === resumed.id)) messages.push(resumed)
        return { ...current, messages }
      })
      const grants = await listAIAuthorizationGrants(activeConversationId)
      setAuthorizationGrants(grants.data)
    } catch {
      setError('授权处理失败，请稍后重试。')
    } finally {
      setAuthorizationBusy(null)
    }
  }

  const revokeGrant = async (grant: AIConversationAuthorizationGrant) => {
    if (authorizationBusy) return
    setAuthorizationBusy(grant.id)
    try {
      await revokeAIAuthorizationGrant(grant.id)
      setAuthorizationGrants((current) => current.filter((item) => item.id !== grant.id))
    } catch {
      setError('撤销授权失败，请稍后重试。')
    } finally {
      setAuthorizationBusy(null)
    }
  }

  const toggleTool = (name: string) => {
    setEnabledTools((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name])
  }

  return (
    <ConsolePageShell
      eyebrow="AI 工作台"
      title="小说分析对话"
      description="以受控、只读工具辅助人物介绍、剧情解析与世界观提炼。工具结果会作为引用附在回答中，敏感数据不会进入对话。"
    >
      <div className="grid min-h-[680px] overflow-hidden rounded-2xl border border-border/80 bg-card shadow-[0_20px_60px_-35px_hsl(var(--foreground)/0.45)] lg:grid-cols-[290px_minmax(0,1fr)]">
        <aside className="border-b border-border bg-[linear-gradient(160deg,hsl(var(--muted)/0.52),hsl(var(--background)/0.82))] lg:border-b-0 lg:border-r">
          <div className="border-b border-border p-4">
            <Button className="w-full" onClick={() => void createConversation()} disabled={sending}>新建对话</Button>
          </div>
          <div className="max-h-[290px] space-y-1 overflow-y-auto p-3 lg:max-h-[610px]">
            <PaginatedListControls
              pagination={pagination}
              empty={!loadingConversations && conversations.length === 0}
              loadingLabel="正在加载对话…"
              errorLabel="加载 AI 对话失败，请稍后重试。"
              emptyLabel="尚无对话，点击“新建对话”开始分析。"
              searchLabel="搜索对话"
            >
              {conversations.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => void switchConversation(item.id)}
                  className={`w-full rounded-lg border px-3 py-3 text-left transition-colors ${item.id === activeConversationId ? 'border-primary/40 bg-primary text-primary-foreground shadow-sm' : 'border-transparent hover:border-border hover:bg-accent'}`}
                >
                  <span className="block truncate text-sm font-semibold">{item.title}</span>
                  <span className={`mt-1 block text-xs ${item.id === activeConversationId ? 'text-primary-foreground/75' : 'text-muted-foreground'}`}><MessageTime value={item.created_at} locale={locale} compact /></span>
                </button>
              ))}
            </PaginatedListControls>
          </div>
          <div className="border-t border-border p-4 text-xs leading-5 text-muted-foreground">
            <p className="font-semibold text-foreground">工具边界</p>
            <p className="mt-1">仅可调用已列出的只读工具，不执行网页抓取、写入书源或任意代码。</p>
          </div>
        </aside>

        <section className="flex min-w-0 flex-col">
          <header className="border-b border-border bg-card/90 px-5 py-4 backdrop-blur">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">受控 Agent 对话</p>
            <h2 className="mt-1 font-serif text-xl font-semibold tracking-tight">{conversation?.title ?? '选择或新建一个对话'}</h2>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              <label className="text-xs font-medium text-muted-foreground">选择书籍
                <select aria-label="选择书籍" value={selectedBookId} onChange={(event) => setSelectedBookId(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm font-normal text-foreground outline-none focus:ring-2 focus:ring-ring">
                  <option value="">不绑定书籍</option>
                  {books.map((book) => <option key={book.id} value={book.id}>{book.book_name}</option>)}
                </select>
              </label>
              <label className="text-xs font-medium text-muted-foreground">选择模型
                <select aria-label="选择模型" value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm font-normal text-foreground outline-none focus:ring-2 focus:ring-ring">
                  <option value="">系统路由默认</option>
                  {models.map((item) => <option key={`${item.provider}:${item.model}`} value={item.model}>{item.model} · {item.provider}</option>)}
                </select>
              </label>
            </div>
          </header>

          <div className="min-h-[320px] flex-1 space-y-5 bg-[radial-gradient(circle_at_top_right,hsl(var(--accent)/0.8)_0,transparent_32%),linear-gradient(180deg,hsl(var(--background)/0.5),hsl(var(--muted)/0.2))] p-5">
            <StatusMessage tone="error" message={error} className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2" />
            {authorizationGrants.length > 0 ? (
              <div className="space-y-2">
                {authorizationGrants.map((grant) => (
                  <div key={grant.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-400/35 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
                    <div>
                      <p>{grant.scope === 'conversation' ? t('ai.authorization.activeConversation') : t('ai.authorization.remembered')}</p>
                      <p className="mt-1 text-xs text-amber-50/70">{t('ai.authorization.expires')}: <MessageTime value={grant.expires_at} locale={locale} compact /></p>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => void revokeGrant(grant)} disabled={authorizationBusy === grant.id} aria-label={t('ai.authorization.revoke')}>{t('ai.authorization.revoke')}</Button>
                  </div>
                ))}
              </div>
            ) : null}
            {!loadingConversations && !conversation ? <div className="grid min-h-[250px] place-items-center text-center text-sm text-muted-foreground">新建一个 AI 对话后，即可开始人物、剧情和世界观解析。</div> : null}
            {conversation?.messages.map((message, index) => (
              <article key={message.id} className={`max-w-3xl ${message.role === 'user' ? 'ml-auto' : ''}`}>
                <div className={`rounded-xl border px-4 py-3 shadow-sm ${message.role === 'user' ? 'border-primary bg-primary text-primary-foreground' : message.status === 'failed' ? 'border-destructive/40 bg-destructive/5' : 'border-border bg-card'}`}>
                  <div className={`mb-2 flex items-center justify-between gap-3 text-xs ${message.role === 'user' ? 'text-primary-foreground/80' : 'text-muted-foreground'}`}>
                    <span className="font-medium">{message.role === 'user' ? t('你') : `${t('AI')} · ${t(modeLabel[message.mode])}`}</span>
                    <MessageTime value={message.created_at} locale={locale} />
                  </div>
                  <MarkdownMessage content={message.content} className={message.role === 'user' ? 'prose-invert text-primary-foreground prose-a:text-primary-foreground' : ''} />
                  {message.authorization_request && message.status === 'authorization_required' && message.authorization_request.status === 'pending' ? (
                    <div className="mt-4 overflow-hidden rounded-lg border border-amber-400/35 bg-amber-400/10 p-4 text-amber-50 shadow-inner">
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-amber-300/20 text-sm font-bold text-amber-100">!</div>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold">{t('ai.authorization.title')}</p>
                          <p className="mt-1 text-xs leading-5 text-amber-50/80">{message.authorization_request.purpose}</p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {message.authorization_request.tools.map((tool) => {
                              const label = authorizationToolLabels[tool]
                              return <span key={tool} className="rounded-full border border-amber-200/25 bg-amber-100/10 px-2.5 py-1 text-xs">{locale === 'en-US' ? label?.en ?? tool : label?.zh ?? tool}</span>
                            })}
                          </div>
                          <p className="mt-3 text-xs leading-5 text-amber-50/70">{t('ai.authorization.boundary')}</p>
                          <div className="mt-4 flex flex-wrap gap-2">
                            <Button size="sm" onClick={() => void decideAuthorization(message.authorization_request!, 'once')} disabled={authorizationBusy === message.authorization_request.id}>{t('ai.authorization.once')}</Button>
                            <Button size="sm" variant="outline" onClick={() => void decideAuthorization(message.authorization_request!, 'conversation')} disabled={authorizationBusy === message.authorization_request.id}>{t('ai.authorization.conversation')}</Button>
                            <Button size="sm" variant="outline" onClick={() => void decideAuthorization(message.authorization_request!, 'remember')} disabled={authorizationBusy === message.authorization_request.id}>{t('ai.authorization.remember')}</Button>
                            <Button size="sm" variant="ghost" onClick={() => void decideAuthorization(message.authorization_request!, 'deny')} disabled={authorizationBusy === message.authorization_request.id}>{t('ai.authorization.deny')}</Button>
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : null}
                  {message.status === 'failed' && !message.authorization_request ? <Button className="mt-3" size="sm" variant="outline" onClick={() => retryMessage(index)} disabled={sending}>重试</Button> : null}
                </div>
                {message.tool_calls?.length ? (
                  <div className="mt-2 space-y-2 rounded-lg border border-primary/20 bg-accent/35 p-3">
                    <p className="text-xs font-semibold text-primary">引用的工具结果</p>
                    {message.tool_calls.map((tool, toolIndex) => (
                      <details key={`${tool.name}-${toolIndex}`} className="rounded border border-border bg-card px-3 py-2">
                        <summary className="cursor-pointer text-sm font-medium">{toolOptions.find((item) => item.name === tool.name)?.label ?? tool.name}</summary>
                        <div className="mt-2 max-h-72 overflow-auto"><ToolResultRenderer value={tool.result} /></div>
                      </details>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
            {sending ? <p className="text-sm text-muted-foreground">AI 正在整理分析结果…</p> : null}
          </div>

          <div className="border-t border-border bg-card p-4">
            <div className="mb-3 flex flex-wrap gap-2">
              {modes.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  aria-pressed={mode === item.value}
                  onClick={() => setMode(item.value)}
                  className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${mode === item.value ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-background hover:bg-accent'}`}
                  title={item.description}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="mb-3 grid gap-2 rounded-lg border border-border bg-muted/25 p-3 md:grid-cols-3">
              {toolOptions.map((tool) => (
                <label key={tool.name} className="flex cursor-pointer items-start gap-2 text-sm">
                  <input type="checkbox" checked={enabledTools.includes(tool.name)} onChange={() => toggleTool(tool.name)} className="mt-1 accent-primary" />
                  <span><span className="block font-medium">{tool.label}</span><span className="block text-xs leading-5 text-muted-foreground">{tool.detail}</span></span>
                </label>
              ))}
            </div>
            {requiresSourceVersion ? (
              <FormField label={t('书源版本 ID')} htmlFor="ai-source-version-id" help={t('需填写书源版本 ID，仅读取规则概览')} className="mb-3">
                <input id="ai-source-version-id" aria-label={t('书源版本 ID')} value={sourceVersionId} onChange={(event) => setSourceVersionId(event.target.value)} placeholder={t('例如：source-version-123')} className="h-10 w-full rounded-md border bg-background px-3 font-mono text-sm outline-none focus:ring-2 focus:ring-ring" />
              </FormField>
            ) : null}
            <div className="flex gap-3">
              <FormField label={t('输入消息')} htmlFor="ai-message" help={t('使用“{mode}”模式提问；Ctrl / ⌘ + Enter 发送', { mode: t(modeLabel[mode]) })} className="flex-1">
                <textarea
                  id="ai-message"
                  aria-label={t('输入消息')}
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                      event.preventDefault()
                      void send()
                    }
                  }}
                  disabled={!activeConversationId || sending}
                  placeholder={activeConversationId ? t('使用“{mode}”模式提问；Ctrl / ⌘ + Enter 发送', { mode: t(modeLabel[mode]) }) : t('请先新建或选择一个对话')}
                  className="min-h-24 w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm leading-6 outline-none ring-offset-background focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:bg-muted"
                />
              </FormField>
              <FormActions className="self-end"><Button disabled={!canSend} onClick={() => void send()}>{t('发送')}</Button></FormActions>
            </div>
          </div>
        </section>
      </div>
    </ConsolePageShell>
  )
}
