import { apiClient } from '@/api/client'
import type { PaginatedEnvelope, PaginatedStatusQueryParams } from '@/api/types'

export interface NovelListParams extends PaginatedStatusQueryParams {}

export interface NovelTaskRow {
  id: string
  title: string
  status: string
  provider: string
  pipeline: string
}

export async function listNovelTasks(params: NovelListParams = {}): Promise<PaginatedEnvelope<NovelTaskRow>> {
  return apiClient.get<NovelTaskRow[]>('/novel/books', { params })
}
