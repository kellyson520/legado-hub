import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface ProviderRow {
  id: string
  name: string
  status: string
}

export interface QuotaPolicyRow {
  id: string
  scope: string
  dailyCostLimit: number
}

export interface LLMSettings {
  providerName?: string
  provider_name?: string
  baseUrl?: string
  base_url?: string
  model: string
  apiKeyConfigured?: boolean
  api_key_configured?: boolean
}

export async function listProviders() {
  return apiClient.get<ProviderRow[]>('/system/providers') as Promise<ApiEnvelope<ProviderRow[]>>
}

export async function listQuotaPolicies() {
  return apiClient.get<QuotaPolicyRow[]>('/system/quotas') as Promise<ApiEnvelope<QuotaPolicyRow[]>>
}

export function getLLMSettings(): Promise<ApiEnvelope<LLMSettings>> {
  return apiClient.get<LLMSettings>('/system/llm-settings')
}

export function updateLLMSettings(payload: {
  providerName: string
  baseUrl: string
  apiKey: string
  model: string
}): Promise<ApiEnvelope<LLMSettings>> {
  return apiClient.put<LLMSettings>('/system/llm-settings', {
    provider_name: payload.providerName,
    base_url: payload.baseUrl,
    api_key: payload.apiKey,
    model: payload.model,
  })
}
