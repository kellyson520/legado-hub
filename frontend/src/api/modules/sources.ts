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

export async function listBookSources(params: SourceListParams = {}) {
  return apiClient.get<SourceRow[]>('/sources/book_sources', { params }) as Promise<ApiEnvelope<SourceRow[]>>
}
