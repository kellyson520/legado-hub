import { apiClient } from '@/api/client'
import type { ApiEnvelope, PaginatedStatusQueryParams } from '@/api/types'

export interface EngineRunRow {
  id: string
  sourceVersionId?: string
  source_version_id?: string
  grade: string
  stepResults?: Record<string, { passed: boolean; elapsedMs?: number; elapsed_ms?: number }>
  step_results?: Record<string, { passed: boolean; elapsedMs?: number; elapsed_ms?: number }>
}

export interface EngineDeploymentRow {
  id: string
  sourceVersionId?: string
  source_version_id?: string
  status: string
  action: string
}

export interface EngineSourceBuildProbe {
  search_status?: string
  toc_status?: string
  content_status?: string
  sample_title?: string
  failure_reason?: string
}

export interface EngineSourceBuildValidation {
  grade?: string
  quality_score?: number
}

export interface EngineSourceBuildAutonomousBuild {
  decision?: string
  strategy?: string
  trigger?: string
  agent_run_id?: string
  probe?: EngineSourceBuildProbe
  validation?: EngineSourceBuildValidation
}

export interface EngineSourceBuildRow {
  id: string
  source_definition_id?: number
  sourceDefinitionId?: number
  source_type?: string
  sourceType?: string
  source_id?: string
  sourceId?: string
  status: string
  payload: {
    canonical_url?: string
    keyword?: string
    submitted_by?: string
    source_rule?: Record<string, unknown>
    autonomous_build?: EngineSourceBuildAutonomousBuild
    [key: string]: unknown
  }
  created_by?: string
  createdBy?: string
  created_at?: string | null
  createdAt?: string | null
}

export interface EngineSourceBuildSubmission {
  job_id: string
  normalized_url: string
  status: string
  source_version_id: string
  source_version_status: string
}

export interface RegexTestResult {
  match_count: number
  matches: Array<{ match: string; groups: Array<string | undefined>; span: [number, number] }>
  replacement_preview: string | null
  error: string | null
}

export interface EngineListParams extends PaginatedStatusQueryParams {}

export async function listEngineRuns(params: EngineListParams = {}) {
  return apiClient.get<EngineRunRow[]>('/engine/runs', { params }) as Promise<ApiEnvelope<EngineRunRow[]>>
}

export async function listEngineDeployments(params: EngineListParams = {}) {
  return apiClient.get<EngineDeploymentRow[]>('/engine/deployments', { params }) as Promise<ApiEnvelope<EngineDeploymentRow[]>>
}

export function listEngineSourceBuilds(params: EngineListParams = {}): Promise<ApiEnvelope<EngineSourceBuildRow[]>> {
  return apiClient.get<EngineSourceBuildRow[]>('/engine/source-builds', { params })
}

export function submitEngineSourceBuild(payload: {
  url: string
  keyword?: string
}): Promise<ApiEnvelope<EngineSourceBuildSubmission>> {
  return apiClient.post<EngineSourceBuildSubmission>('/engine/source-builds', {
    url: payload.url,
    keyword: payload.keyword ?? '',
  })
}

export function testEngineRegex(payload: { text: string; pattern: string; replacement?: string | null }): Promise<ApiEnvelope<RegexTestResult>> {
  return apiClient.post('/engine/regex-test', payload)
}
