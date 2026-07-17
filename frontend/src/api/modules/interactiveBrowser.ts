import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface InteractiveBrowserSession {
  id: string
  state: string
  target_origin?: string | null
  expires_at?: string | null
  closed_at?: string | null
  terminal_reason?: string | null
}

export function getInteractiveBrowserSession(sessionId: string): Promise<ApiEnvelope<InteractiveBrowserSession>> {
  return apiClient.get(`/interactive-browser/sessions/${sessionId}`)
}

export function createInteractiveBrowserRelayTicket(sessionId: string): Promise<ApiEnvelope<{ relay_path: string }>> {
  return apiClient.post(`/interactive-browser/sessions/${sessionId}/relay-ticket`)
}

export function continueInteractiveBrowserSession(sessionId: string): Promise<ApiEnvelope<{
  validation: { passed: boolean; reason: string; stages: Record<string, unknown> }
}>> {
  return apiClient.post(`/interactive-browser/sessions/${sessionId}/continue`)
}

export function cancelInteractiveBrowserSession(sessionId: string): Promise<ApiEnvelope<InteractiveBrowserSession>> {
  return apiClient.delete<InteractiveBrowserSession>(`/interactive-browser/sessions/${sessionId}`)
}
