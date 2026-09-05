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

export type ProviderType = 'openai_compatible' | 'anthropic' | 'gemini'

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

export interface InteractiveBrowserSettings {
  enabled: boolean
  automaticEnabled: boolean
  maxSessions: number
  sessionTimeoutSeconds: number
}

export interface InteractiveBrowserSettingsInput {
  enabled: boolean
  automaticEnabled: boolean
  maxSessions: number
  sessionTimeoutSeconds: number
}

interface InteractiveBrowserSettingsResponse {
  enabled: boolean
  automatic_enabled: boolean
  max_sessions: number
  session_timeout_seconds: number
}

export interface ProviderConfigurationInput {
  name: string
  providerType?: ProviderType
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

export interface SettingsSection<T extends Record<string, unknown> = Record<string, unknown>> {
  domain: string
  tab: string
  value: T
  version: string | null
  updatedAt?: string | null
  updated_at?: string | null
}

export function listProviders(): Promise<ApiEnvelope<ProviderRow[]>> {
  return apiClient.get<ProviderRow[]>('/system/providers')
}

export function createProvider(payload: ProviderConfigurationInput): Promise<ApiEnvelope<ProviderRow>> {
  return apiClient.post<ProviderRow>('/system/providers', {
    name: payload.name,
    ...(payload.providerType ? { provider_type: payload.providerType } : {}),
    base_url: payload.baseUrl,
    api_key: payload.apiKey,
    default_model: payload.defaultModel,
    enabled: payload.enabled,
  })
}

export function updateProvider(providerId: string, payload: ProviderConfigurationInput): Promise<ApiEnvelope<ProviderRow>> {
  return apiClient.put<ProviderRow>(`/system/providers/${providerId}`, {
    name: payload.name,
    ...(payload.providerType ? { provider_type: payload.providerType } : {}),
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

export function listQuotaPolicies(): Promise<ApiEnvelope<QuotaPolicyRow[]>> {
  return apiClient.get<QuotaPolicyRow[]>('/system/quotas')
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

export function getSettingsSection<T extends Record<string, unknown> = Record<string, unknown>>(
  domain: string,
  tab: string,
): Promise<ApiEnvelope<SettingsSection<T>>> {
  return apiClient.get<SettingsSection<T>>(`/system/settings/${domain}/${tab}`)
}

export function saveSettingsSection<T extends Record<string, unknown> = Record<string, unknown>>(
  domain: string,
  tab: string,
  value: T,
  expectedVersion: string | null,
): Promise<ApiEnvelope<SettingsSection<T>>> {
  return apiClient.put<SettingsSection<T>>(`/system/settings/${domain}/${tab}`, {
    value,
    expected_version: expectedVersion,
  })
}

function mapInteractiveBrowserSettings(settings: InteractiveBrowserSettingsResponse): InteractiveBrowserSettings {
  return {
    enabled: settings.enabled,
    automaticEnabled: settings.automatic_enabled,
    maxSessions: settings.max_sessions,
    sessionTimeoutSeconds: settings.session_timeout_seconds,
  }
}

export async function getInteractiveBrowserSettings(): Promise<ApiEnvelope<InteractiveBrowserSettings>> {
  const response = await apiClient.get<InteractiveBrowserSettingsResponse>('/system/interactive-browser-settings')
  return {
    ...response,
    data: mapInteractiveBrowserSettings(response.data),
  }
}

export async function updateInteractiveBrowserSettings(
  payload: InteractiveBrowserSettingsInput,
): Promise<ApiEnvelope<InteractiveBrowserSettings>> {
  const response = await apiClient.put<InteractiveBrowserSettingsResponse>('/system/interactive-browser-settings', {
    enabled: payload.enabled,
    automatic_enabled: payload.automaticEnabled,
    max_sessions: payload.maxSessions,
    session_timeout_seconds: payload.sessionTimeoutSeconds,
  })
  return {
    ...response,
    data: mapInteractiveBrowserSettings(response.data),
  }
}
