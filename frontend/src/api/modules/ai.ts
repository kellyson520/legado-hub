import { apiClient } from '@/api/client'
import type { ApiEnvelope, PaginatedEnvelope, PaginatedStatusQueryParams } from '@/api/types'

export interface AIListParams extends PaginatedStatusQueryParams {}

export type AIWorkspaceMode = 'chat' | 'character' | 'storyline' | 'world'

export interface AIWorkspaceToolCall {
  name: string
  arguments: Record<string, unknown>
  result: unknown
}

export type AIConversationAuthorizationDecision = 'once' | 'conversation' | 'remember' | 'deny'

export interface AIConversationAuthorizationRequest {
  id: string
  message_id?: string
  conversation_id?: string
  tools: string[]
  purpose: string
  status: string
  decision?: AIConversationAuthorizationDecision | null
  expires_at?: string | null
  resolved_at?: string | null
  result_message_id?: string | null
  choices?: AIConversationAuthorizationDecision[]
}

export interface AIConversationAuthorizationGrant {
  id: string
  scope: 'conversation' | 'remembered'
  conversation_id?: string | null
  tools: string[]
  expires_at: string
  revoked_at?: string | null
}

export interface AIConversationMessage {
  id: string
  role: 'user' | 'assistant'
  mode: AIWorkspaceMode
  content: string
  status: 'succeeded' | 'failed' | 'authorization_required' | 'denied'
  tool_calls: AIWorkspaceToolCall[]
  metadata?: Record<string, unknown>
  authorization_request?: AIConversationAuthorizationRequest
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
  authorization_requests?: AIConversationAuthorizationRequest[]
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

export async function listAITasks(params: AIListParams = {}) {
  const response = await apiClient.get<BackendAITaskRow[]>('/ai/tasks', { params })
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
  } satisfies PaginatedEnvelope<AITaskRow>
}

export function listAIConversations(params: AIListParams = {}): Promise<PaginatedEnvelope<AIConversationSummary>> {
  return apiClient.get('/ai/conversations', { params })
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

export function decideAIConversationAuthorization(
  conversationId: string,
  requestId: string,
  payload: { decision: AIConversationAuthorizationDecision },
): Promise<ApiEnvelope<{ authorization: AIConversationAuthorizationRequest; next_authorization?: AIConversationAuthorizationRequest; message?: AIConversationMessage }>> {
  return apiClient.post(`/ai/conversations/${conversationId}/authorization-requests/${requestId}/decision`, payload)
}

export function listAIConversationAuthorizations(conversationId: string): Promise<ApiEnvelope<AIConversationAuthorizationRequest[]>> {
  return apiClient.get(`/ai/conversations/${conversationId}/authorization-requests`, { params: { status: 'pending' } })
}

export function listAIAuthorizationGrants(conversationId?: string): Promise<ApiEnvelope<AIConversationAuthorizationGrant[]>> {
  return apiClient.get('/ai/authorization-grants', { params: conversationId ? { conversation_id: conversationId } : undefined })
}

export function revokeAIAuthorizationGrant(grantId: string): Promise<ApiEnvelope<AIConversationAuthorizationGrant>> {
  return apiClient.post(`/ai/authorization-grants/${grantId}/revoke`)
}
