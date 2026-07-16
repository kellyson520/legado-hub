import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface SourceRow {
  id: number | string
  bookSourceName: string
  bookSourceUrl: string
  bookSourceGroup: string
  enabled: boolean
  sourceStatus: string
  sourceOrigin: string | null
  lastCheckTime: string | null
  errorMsg: string | null
  payload?: Record<string, unknown>
}

export interface SourceListParams {
  page?: number
  page_size?: number
  search?: string
}

export interface LegadoImportItem {
  index: number
  status: 'created' | 'invalid' | 'skipped_duplicate'
  source_url?: string
  source_version_id?: string
  reason?: string
}

export interface LegadoSource {
  bookSourceName: string
  bookSourceUrl: string
  [key: string]: unknown
}

export interface SourceValidationStep {
  passed: boolean
  elapsed_ms?: number
  status?: string
}

export interface SourceVersionResponse {
  source_version_id: string
  source_type: string
  source_id: string
  status: string
  payload: Record<string, unknown>
  created_by?: string
  created_at?: string | null
  latest_validation?: {
    id: string
    trigger: string
    score: number
    grade: string
    step_results: Record<string, SourceValidationStep>
    diagnostics: string[]
    created_at?: string | null
  } | null
  content_status: string
  publish_allowed: boolean
}

export async function listBookSources(params: SourceListParams = {}) {
  return apiClient.get<SourceRow[]>('/sources/visible', { params }) as Promise<ApiEnvelope<SourceRow[]>>
}

export function importLegadoSources(payload: LegadoSource | LegadoSource[]): Promise<ApiEnvelope<{ items: LegadoImportItem[] }>> {
  return apiClient.post('/sources/import', payload)
}

export function importLegadoSourceFile(file: File): Promise<ApiEnvelope<{ items: LegadoImportItem[] }>> {
  const formData = new FormData()
  formData.append('file', file, file.name)
  return apiClient.post('/sources/import/file', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function exportLegadoSources(): Promise<ApiEnvelope<LegadoSource[]>> {
  return apiClient.get('/sources/export')
}

export function getSourceVersion(sourceVersionId: string): Promise<ApiEnvelope<SourceVersionResponse>> {
  return apiClient.get(`/sources/versions/${sourceVersionId}`)
}

export function createSourceDraft(
  sourceVersionId: string,
  payload: Record<string, unknown>
): Promise<ApiEnvelope<SourceVersionResponse>> {
  return apiClient.post(`/sources/versions/${sourceVersionId}/drafts`, payload)
}

export function validateSourceVersion(sourceVersionId: string): Promise<ApiEnvelope<SourceVersionResponse>> {
  return apiClient.post(`/sources/versions/${sourceVersionId}/validate`)
}

export function publishSourceVersion(sourceVersionId: string): Promise<ApiEnvelope<SourceVersionResponse>> {
  return apiClient.post(`/sources/versions/${sourceVersionId}/publish`)
}
