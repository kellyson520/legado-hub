import { apiClient, getConfiguredAccessToken } from '@/api/client'
import type { ApiEnvelope, PaginatedEnvelope, PaginatedStatusQueryParams } from '@/api/types'

export interface NovelListParams extends PaginatedStatusQueryParams {}

export interface NovelReadingProgress {
  owner_scope?: string
  book_id?: number
  chapter_id: number
  chapter_title?: string
  offset_chars: number
  percent: number
  theme?: string
  background?: string
  font_size?: number
  line_height?: number
  content_width?: 'compact' | 'comfortable'
  updated_at?: string
}

export interface NovelBook {
  id: number
  book_url?: string
  book_name: string
  author?: string
  source_name?: string
  source_type?: string
  total_chapters?: number
  total_words?: number
  status?: string
  ingest_progress?: number
  ingest_error_msg?: string | null
  character_count?: number
  entity_count?: number
  event_count?: number
  relationship_count?: number
  summary_global?: string
  created_at?: string
  updated_at?: string
  progress?: NovelReadingProgress | null
}

export interface NovelChapter {
  id: number
  book_id: number
  canonical_type?: string
  canonical_num?: number
  canonical_full?: string
  raw_title?: string
  parsed_title_core?: string
  raw_chapter_num?: string
  source_volume?: string
  chapter_num?: number
  chapter_title: string
  word_count?: number
  quality_score?: number
  summary?: string
  key_events?: string[]
  character_appearances?: Record<string, number>
  location_appearances?: Record<string, number>
  mood_tags?: string[]
  arc_tag?: string
  arc_summary?: string
  raw_text?: string
}

export interface NovelSearchResult {
  sourceId: number
  bookUrl: string
  name: string
  author: string
  sourceName?: string
  sourceUrl?: string
  healthStatus?: string
}

export interface NovelImportWarning {
  code: string
  message: string
  chapter_index?: number | null
}

export interface NovelImportChapterPreview {
  ordinal: number
  title: string
  word_count: number
  content_hash?: string
  preview?: string
}

export interface NovelImportPreview {
  content_hash: string
  title: string
  author: string
  media_type: string
  total_chars: number
  chapters: NovelImportChapterPreview[]
  warnings: NovelImportWarning[]
}

export interface NovelImportResult {
  book_id: number
  duplicate?: boolean
  status: string
  task_id?: string
  error_code?: string | null
  preview?: NovelImportPreview
}

export interface NovelConversationSummary {
  id: string
  title: string
  created_at: string
  book_id?: number | null
  chapter_id?: number | null
  entrypoint?: 'workspace' | 'book' | 'reader'
  model_ref?: string | null
}

export interface NovelConversationMessage {
  id: string
  role: 'user' | 'assistant'
  mode: 'chat' | 'character' | 'storyline' | 'world'
  content: string
  status?: 'succeeded' | 'failed'
  tool_calls?: Array<{ name: string; arguments?: Record<string, unknown>; result?: unknown }>
  citations?: Array<{ title?: string; chapter?: string; evidence?: string; confidence?: number }>
  created_at: string
  book_id?: number | null
  chapter_id?: number | null
  entrypoint?: 'workspace' | 'book' | 'reader'
}

export interface NovelConversation extends NovelConversationSummary {
  messages: NovelConversationMessage[]
}

export interface NovelCharacterListItem {
  name: string
  role: string
  importance_tier: string
  overall_tier: string
  aliases: string[]
  summary: string
  avatar_tag?: string
  items_count: number
  events_count: number
  relationships_count: number
}

export interface CharacterRelationship {
  target: string
  relation: string
  affinity?: number
  description: string
}

export interface CharacterEvent {
  chapter: string
  title: string
  description: string
}

export interface CharacterItem {
  name: string
  action: string
  desc: string
}

export interface NovelCharacterDossier {
  name: string
  role: string
  importance_tier: string
  overall_tier: string
  aliases: string[]
  summary: string
  avatar_tag?: string
  alignment?: string
  personal_info?: {
    gender?: string
    identity?: string
    status?: string
    mentality?: string
  }
  relationships: CharacterRelationship[]
  events: CharacterEvent[]
  items: CharacterItem[]
  canonical_excerpts?: Array<{ chapter: string; text: string }>
}

export interface NovelModelOption {
  provider: string
  model: string
}

export interface NovelModels {
  novel_chat?: NovelModelOption[]
  novel_extract?: NovelModelOption[]
  novel_summary?: NovelModelOption[]
  novel_embedding?: NovelModelOption[]
}

export interface NovelAssistantPayload {
  content: string
  entrypoint?: 'workspace' | 'book' | 'reader'
  bookId?: number
  chapterId?: number
  mode?: 'chat' | 'character' | 'storyline' | 'world'
  model?: string
  stream?: boolean
}

export interface NovelSseEvent {
  event: 'started' | 'delta' | 'citation' | 'usage' | 'completed' | 'error'
  data: Record<string, unknown>
}

export interface NovelTaskRow {
  id: string
  title: string
  status: string
  provider: string
  pipeline: string
}

function normalizeProgress(value: NovelReadingProgress | null | undefined) {
  if (!value) return value
  const raw = value as NovelReadingProgress & Record<string, unknown>
  return {
    ...value,
    chapter_id: Number(raw.chapter_id ?? value.chapter_id ?? 0),
    offset_chars: Number(raw.offset_chars ?? value.offset_chars ?? 0),
    percent: Number(raw.percent ?? value.percent ?? 0),
    theme: String(raw.theme ?? value.theme ?? 'paper'),
    background: String(raw.background ?? value.background ?? ''),
    font_size: Number(raw.font_size ?? value.font_size ?? 18),
  }
}

function normalizeBook(book: NovelBook): NovelBook {
  return {
    ...book,
    id: Number(book.id),
    progress: normalizeProgress(book.progress),
  }
}

function normalizeSearchResult(item: Record<string, unknown>): NovelSearchResult {
  return {
    sourceId: Number(item.sourceId ?? item.source_id ?? 0),
    bookUrl: String(item.bookUrl ?? item.book_url ?? ''),
    name: String(item.name ?? item.book_name ?? ''),
    author: String(item.author ?? ''),
    sourceName: item.sourceName == null ? undefined : String(item.sourceName),
    sourceUrl: item.sourceUrl == null ? undefined : String(item.sourceUrl),
    healthStatus: item.healthStatus == null && item.health_status == null
      ? undefined
      : String(item.healthStatus ?? item.health_status),
  }
}

function progressPayload(progress: {
  chapterId: number
  offsetChars: number
  percent: number
  preferences?: Record<string, unknown>
}) {
  return {
    chapter_id: progress.chapterId,
    offset_chars: progress.offsetChars,
    percent: progress.percent,
    preferences: progress.preferences ?? {},
  }
}

function messagePayload(payload: NovelAssistantPayload) {
  return {
    content: payload.content,
    entrypoint: payload.entrypoint ?? 'workspace',
    book_id: payload.bookId,
    chapter_id: payload.chapterId,
    mode: payload.mode ?? 'chat',
    model: payload.model,
    stream: payload.stream ?? false,
  }
}

export async function listNovelBooks() {
  const response = await apiClient.get<NovelBook[]>('/novel/books') as ApiEnvelope<NovelBook[]>
  return { ...response, data: response.data.map(normalizeBook) } satisfies ApiEnvelope<NovelBook[]>
}

export async function searchNovelBooks(keyword: string) {
  const response = await apiClient.post<Record<string, unknown>[]>('/reading/search', {
    keyword: keyword.trim(),
    limit_per_source: 5,
  }) as ApiEnvelope<Record<string, unknown>[]>
  return { ...response, data: response.data.map(normalizeSearchResult) } satisfies ApiEnvelope<NovelSearchResult[]>
}

function novelFileForm(file: File) {
  const form = new FormData()
  form.append('file', file)
  return form
}

export async function previewNovel(file: File) {
  return apiClient.post<NovelImportPreview>('/novel/books/import/preview', novelFileForm(file), {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export async function uploadNovel(file: File) {
  return apiClient.post<NovelImportResult>('/novel/books/import/upload', novelFileForm(file), {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function importNovelFromSource(result: Pick<NovelSearchResult, 'sourceId' | 'bookUrl' | 'name' | 'author'>) {
  return apiClient.post<NovelImportResult>('/novel/books/import/source', {
    source_id: result.sourceId,
    book_url: result.bookUrl,
    book_name: result.name,
    author: result.author,
  })
}

export function importNovelFromUrl(url: string, title = '', author = '') {
  return apiClient.post<NovelImportResult>('/novel/books/import/url', { url, title, author })
}

export function getNovelBook(bookId: number | string) {
  return apiClient.get<NovelBook>(`/novel/books/${bookId}`)
}

export function listNovelChapters(bookId: number | string) {
  return apiClient.get<NovelChapter[]>(`/novel/books/${bookId}/chapters`)
}

export function listNovelCharacters(bookId: number | string) {
  return apiClient.get<NovelCharacterListItem[]>(`/novel/books/${bookId}/characters`)
}

export function getNovelCharacterDossier(bookId: number | string, characterName: string) {
  return apiClient.get<NovelCharacterDossier>(`/novel/books/${bookId}/characters/${encodeURIComponent(characterName)}/dossier`)
}

export function getNovelChapter(bookId: number | string, chapterId: number | string) {
  return apiClient.get<NovelChapter>(`/novel/books/${bookId}/chapters/${chapterId}`)
}

export function getNovelProgress(bookId: number | string) {
  return apiClient.get<NovelReadingProgress | null>(`/novel/books/${bookId}/progress`)
}

export function saveNovelProgress(bookId: number | string, progress: {
  chapterId: number
  offsetChars: number
  percent: number
  preferences?: Record<string, unknown>
}) {
  return apiClient.put<NovelReadingProgress>(`/novel/books/${bookId}/progress`, progressPayload(progress))
}

export function createNovelConversation(payload: {
  title?: string
  bookId?: number
  entrypoint?: 'workspace' | 'book' | 'reader'
  model?: string
  chapterId?: number
}) {
  return apiClient.post<NovelConversation>('/novel/conversations', {
    title: payload.title,
    book_id: payload.bookId,
    entrypoint: payload.entrypoint ?? 'workspace',
    model: payload.model,
    chapter_id: payload.chapterId,
  })
}

export function getNovelConversation(conversationId: string) {
  return apiClient.get<NovelConversation>(`/novel/conversations/${conversationId}`)
}

export function listNovelModels() {
  return apiClient.get<NovelModels>('/novel/models')
}

export function listNovelTools(bookId?: number) {
  return apiClient.get<Array<Record<string, unknown>>>('/novel/tools', bookId == null ? undefined : { params: { book_id: bookId } })
}

export function sendNovelMessage(conversationId: string, payload: NovelAssistantPayload) {
  return apiClient.post<NovelConversationMessage>(
    `/novel/conversations/${conversationId}/messages`,
    messagePayload(payload),
  )
}

export function parseNovelSse(input: string): NovelSseEvent[] {
  const allowed = new Set<NovelSseEvent['event']>(['started', 'delta', 'citation', 'usage', 'completed', 'error'])
  return input
    .split(/\r?\n\r?\n/)
    .map((block) => {
      const event = block.match(/^event:\s*([^\n]+)$/m)?.[1]?.trim()
      const dataLines = [...block.matchAll(/^data:\s?(.*)$/gm)].map((match) => match[1])
      if (!event || !allowed.has(event as NovelSseEvent['event']) || dataLines.length === 0) return null
      try {
        const data = JSON.parse(dataLines.join('\n')) as Record<string, unknown>
        return { event: event as NovelSseEvent['event'], data }
      } catch {
        return { event: 'error', data: { message: '无法解析助手流响应' } } satisfies NovelSseEvent
      }
    })
    .filter((item): item is NovelSseEvent => item !== null)
}

export async function* streamNovelMessage(conversationId: string, payload: NovelAssistantPayload): AsyncGenerator<NovelSseEvent> {
  const response = await fetch(`/api/novel/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(getConfiguredAccessToken() ? { Authorization: `Bearer ${getConfiguredAccessToken()}` } : {}),
    },
    body: JSON.stringify(messagePayload({ ...payload, stream: true })),
  })
  if (!response.ok || !response.body) throw new Error(`Novel assistant stream failed: ${response.status}`)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const next = await reader.read()
    buffer += decoder.decode(next.value ?? new Uint8Array(), { stream: !next.done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    for (const event of parseNovelSse(blocks.join('\n\n'))) yield* event ? [event] : []
    if (next.done) break
  }
  for (const event of parseNovelSse(buffer)) yield event
}

export async function listNovelTasks(params: NovelListParams = {}): Promise<PaginatedEnvelope<NovelTaskRow>> {
  const response = await apiClient.get<Array<NovelBook | NovelTaskRow>>('/novel/books', { params })
  return {
    ...response,
    data: response.data.map((item) => 'book_name' in item
      ? {
          id: String(item.id),
          title: item.book_name,
          status: item.status ?? 'unknown',
          provider: item.source_name ?? 'n/a',
          pipeline: 'novel-index',
        }
      : { ...item, id: String(item.id) }),
  } satisfies PaginatedEnvelope<NovelTaskRow>
}
