import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface ProviderRow {
  id: string
  name: string
  status: string
  providerType?: string
  provider_type?: string
  baseUrl?: string
  base_url?: string
  defaultModel?: string
  default_model?: string
  enabled?: boolean
  apiKeyConfigured?: boolean
  api_key_configured?: boolean
  apiKeyMasked?: string
  api_key_masked?: string
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

export interface SourceBuildAgentSettings {
  enabled: boolean
  providerConfigured?: boolean
  provider_configured?: boolean
}

export interface ProviderConfigurationInput {
  name: string
  baseUrl: string
  apiKey: string
  defaultModel: string
  enabled: boolean
}

export interface ProviderRouteEntry {
  id?: string
  providerAccountId?: string
  provider_account_id?: string
  providerName?: string
  provider_name?: string
  model: string
  priority?: number
  enabled: boolean
}

export interface ProviderRoute {
  group: string
  entries: ProviderRouteEntry[]
}

export interface NovelUsageMetrics {
  requests: number
  cache_hits: number
  cache_misses: number
  input_tokens: number
  output_tokens: number
  cost: number
  evidence_count: number
  providers: string[]
  models: Record<string, string[]>
}

export interface NovelSettings {
  vector_backend?: string
  endpoint?: string
  collection_prefix?: string
  dimension?: number
  embedding_model?: string
  batch_size?: number
  threshold?: number
  concurrency?: number
  retries?: number
  cache_ttl?: number
  enabled_tools?: string[]
  chapter_size?: number
  index_policy?: string
  cost_budget_daily?: number
  cost_budget_per_request?: number
  credential_configured?: boolean
  credential_masked?: string
  route_groups?: Record<string, Array<{ provider: string; model: string; enabled: boolean }>>
  models?: Record<string, string[]>
  metrics?: NovelUsageMetrics
}

export async function listProviders() {
  return apiClient.get<ProviderRow[]>('/system/providers') as Promise<ApiEnvelope<ProviderRow[]>>
}

export function createProvider(payload: ProviderConfigurationInput): Promise<ApiEnvelope<ProviderRow>> {
  return apiClient.post<ProviderRow>('/system/providers', {
    name: payload.name,
    base_url: payload.baseUrl,
    api_key: payload.apiKey,
    default_model: payload.defaultModel,
    enabled: payload.enabled,
  })
}

export function updateProvider(providerId: string, payload: ProviderConfigurationInput): Promise<ApiEnvelope<ProviderRow>> {
  return apiClient.put<ProviderRow>(`/system/providers/${providerId}`, {
    name: payload.name,
    base_url: payload.baseUrl,
    api_key: payload.apiKey,
    default_model: payload.defaultModel,
    enabled: payload.enabled,
  })
}

export function discoverProviderModels(providerId: string): Promise<ApiEnvelope<string[]>> {
  return apiClient.post<string[]>(`/system/providers/${providerId}/models`)
}

export function getProviderRoute(group: string): Promise<ApiEnvelope<ProviderRoute>> {
  return apiClient.get<ProviderRoute>(`/system/provider-routes/${group}`)
}

export function updateProviderRoute(
  group: string,
  payload: { entries: Array<{ providerAccountId: string; model: string; enabled: boolean }> },
): Promise<ApiEnvelope<ProviderRoute>> {
  return apiClient.put<ProviderRoute>(`/system/provider-routes/${group}`, {
    entries: payload.entries.map((entry) => ({
      provider_account_id: entry.providerAccountId,
      model: entry.model,
      enabled: entry.enabled,
    })),
  })
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

export function getSourceBuildAgentSettings(): Promise<ApiEnvelope<SourceBuildAgentSettings>> {
  return apiClient.get<SourceBuildAgentSettings>('/system/source-build-agent-settings')
}

export function updateSourceBuildAgentSettings(payload: {
  enabled: boolean
}): Promise<ApiEnvelope<SourceBuildAgentSettings>> {
  return apiClient.put<SourceBuildAgentSettings>('/system/source-build-agent-settings', payload)
}

export function getNovelSettings(): Promise<ApiEnvelope<NovelSettings>> {
  return apiClient.get<NovelSettings>('/system/novel-settings')
}

export function updateNovelSettings(payload: Partial<NovelSettings>): Promise<ApiEnvelope<NovelSettings>> {
  return apiClient.put<NovelSettings>('/system/novel-settings', payload)
}
