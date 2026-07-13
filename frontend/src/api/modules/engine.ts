import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

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

export async function listEngineRuns() {
  return apiClient.get<EngineRunRow[]>('/engine/runs') as Promise<ApiEnvelope<EngineRunRow[]>>
}

export async function listEngineDeployments() {
  return apiClient.get<EngineDeploymentRow[]>('/engine/deployments') as Promise<ApiEnvelope<EngineDeploymentRow[]>>
}

export function listEngineSourceBuilds(): Promise<ApiEnvelope<EngineSourceBuildRow[]>> {
  return apiClient.get<EngineSourceBuildRow[]>('/engine/source-builds')
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
