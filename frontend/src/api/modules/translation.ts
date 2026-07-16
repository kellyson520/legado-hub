import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface TranslationListParams {
  page?: number
  page_size?: number
  search?: string
  status?: string
}

export interface TranslationJobRow {
  id: string
  name: string
  status: string
  provider: string
  targetLanguage: string
  progress: string
}

interface BackendTranslationJobRow {
  id: string
  name?: string
  status: string
  provider?: string
  targetLanguage?: string
  target_language?: string
  source_language?: string
  progress?: string
}

export async function listTranslationJobs(params: TranslationListParams = {}) {
  const response = (await apiClient.get<BackendTranslationJobRow[]>('/translation/jobs', { params })) as ApiEnvelope<
    BackendTranslationJobRow[]
  >
  return {
    ...response,
    data: response.data.map((job) => {
      const sourceLanguage = job.source_language ?? 'source'
      const targetLanguage = job.targetLanguage ?? job.target_language ?? 'target'
      return {
        id: job.id,
        name: job.name ?? `${sourceLanguage}→${targetLanguage}`,
        status: job.status,
        provider: job.provider ?? 'n/a',
        targetLanguage,
        progress: job.progress ?? '0%',
      }
    }),
  } satisfies ApiEnvelope<TranslationJobRow[]>
}
