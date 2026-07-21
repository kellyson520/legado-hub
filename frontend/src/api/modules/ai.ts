import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export type AIWorkspaceMode = 'chat' | 'character' | 'storyline' | 'world'

export interface AIWorkspaceToolCall {
  name: string
  arguments: Record<string, string>
  result: unknown
}

export interface AIConversationMessage {
  id: string
  role: 'user' | 'assistant'
  mode: AIWorkspaceMode
  content: string
  status: 'succeeded' | 'failed'
  tool_calls: AIWorkspaceToolCall[]
  created_at: string
  entrypoint?: 'workspace' | 'book' | 'reader'
  book_id?: number | null
  chapter_id?: number | null
}

export interface AIConversationSummary {
  id: string
  title: string
  created_at: string
  book_id?: number | null
  entrypoint?: 'workspace' | 'book' | 'reader'
  model_ref?: string | null
}

export interface AIConversation extends AIConversationSummary {
  messages: AIConversationMessage[]
}

export interface AITaskRow {
  id: string
  name: string
  status: string
  provider: string
  model: string
  cost: string
}

interface BackendAITaskRow {
  id: string
  name?: string
  type?: string
  status: string
  provider?: string
  model?: string
  cost?: number | string
}

export async function listAITasks() {
  const response = (await apiClient.get<BackendAITaskRow[]>('/ai/tasks')) as ApiEnvelope<BackendAITaskRow[]>
  return {
    ...response,
    data: response.data.map((task) => ({
      id: task.id,
      name: task.name ?? task.type ?? task.id,
      status: task.status,
      provider: task.provider ?? 'n/a',
      model: task.model ?? 'n/a',
      cost: typeof task.cost === 'number' ? `$${task.cost.toFixed(2)}` : (task.cost ?? '$0.00'),
    })),
  } satisfies ApiEnvelope<AITaskRow[]>
}

export function listAIConversations(): Promise<ApiEnvelope<AIConversationSummary[]>> {
  return apiClient.get('/ai/conversations')
}

export function createAIConversation(payload: {
  title?: string
  book_id?: number
  entrypoint?: 'workspace' | 'book' | 'reader'
  model?: string
}): Promise<ApiEnvelope<AIConversationSummary>> {
  return apiClient.post('/ai/conversations', payload)
}

export function getAIConversation(conversationId: string): Promise<ApiEnvelope<AIConversation>> {
  return apiClient.get(`/ai/conversations/${conversationId}`)
}

export function sendAIConversationMessage(
  conversationId: string,
  payload: {
    content: string
    mode: AIWorkspaceMode
    tool_requests?: Array<{ name: string; arguments: Record<string, string> }>
    source_version_id?: string
    entrypoint?: 'workspace' | 'book' | 'reader'
    book_id?: number
    chapter_id?: number
    model?: string
    stream?: boolean
  }
): Promise<ApiEnvelope<AIConversationMessage>> {
  return apiClient.post(`/ai/conversations/${conversationId}/messages`, payload)
}
