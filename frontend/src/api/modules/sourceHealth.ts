import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface SourceHealthRow {
  source_id: number
  source_name: string
  source_url: string
  health_status: string
  search_status: string
  toc_status: string
  content_status: string
  failure_reason: string
  route_policy: string
  route_score?: number
  last_probe_at?: string | null
  next_probe_at?: string | null
}

export interface SourceProbeStage {
  status: string
  elapsed_ms?: number
  request_preview?: string
  response_kind?: string
  error_message?: string
  detail: Record<string, unknown>
}

export interface SourceProbeRun {
  id: string
  source_id: number
  keyword: string
  overall_status: string
  failure_reason: string
  created_at: string | null
  search_result: SourceProbeStage
  toc_result: SourceProbeStage
  content_result: SourceProbeStage
  summary: Record<string, unknown>
}

export interface SourceFailureEvent {
  at: string | null
  stage: string
  status: string
  reason: string
  message: string
  request_preview: string
  http_status: number | null
  response_kind: string
}

export interface SourceHealthDetail {
  snapshot: SourceHealthRow | null
  runs: SourceProbeRun[]
  route_decision: {
    policy: string
    score: number
    reason: string
  }
  failure_timeline: SourceFailureEvent[]
}

export async function listSourceHealth(params: { page?: number; page_size?: number; statuses?: string } = {}) {
  return apiClient.get<SourceHealthRow[]>('/source-health/book-sources', {
    params,
  }) as Promise<ApiEnvelope<SourceHealthRow[]>>
}

export async function getSourceHealth(sourceId: number) {
  return apiClient.get<SourceHealthDetail>(`/source-health/book-sources/${sourceId}`)
}

export async function probeSourceHealth(sourceId: number, keywordSamples = ['捞尸人', '斗罗大陆']) {
  return apiClient.post(`/source-health/book-sources/${sourceId}/probe`, {
    keyword_samples: keywordSamples,
    probe_mode: 'full_chain',
  })
}

export async function recoverSourceHealth(sourceId: number) {
  return apiClient.post(`/source-health/book-sources/${sourceId}/recover`)
}
