import { apiClient } from '@/api/client'
import type { ApiEnvelope, PaginatedStatusQueryParams } from '@/api/types'

export interface NovelListParams extends PaginatedStatusQueryParams {}

export interface NovelTaskRow {
  id: string
  title: string
  status: string
  provider: string
  pipeline: string
}

export async function listNovelTasks(params: NovelListParams = {}) {
  return apiClient.get<NovelTaskRow[]>('/novel/books', { params }) as Promise<ApiEnvelope<NovelTaskRow[]>>
}
