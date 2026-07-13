import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface NovelTaskRow {
  id: string
  title: string
  status: string
  provider: string
  pipeline: string
}

export async function listNovelTasks() {
  return apiClient.get<NovelTaskRow[]>('/novel/books') as Promise<ApiEnvelope<NovelTaskRow[]>>
}
