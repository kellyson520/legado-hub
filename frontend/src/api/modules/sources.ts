import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface SourceRow {
  id: string
  name: string
  status: string
  publishedVersion: string
  latestGrade: string
}

export interface SourceListParams {
  page?: number
  page_size?: number
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

export async function listBookSources(params: SourceListParams = {}) {
  return apiClient.get<SourceRow[]>('/sources/book_sources', { params }) as Promise<ApiEnvelope<SourceRow[]>>
}

export function importLegadoSources(payload: LegadoSource | LegadoSource[]): Promise<ApiEnvelope<{ items: LegadoImportItem[] }>> {
  return apiClient.post('/sources/import', payload)
}

export function exportLegadoSources(): Promise<ApiEnvelope<LegadoSource[]>> {
  return apiClient.get('/sources/export')
}
