import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface AITaskRow {
  id: string
  name: string
  status: string
  provider: string
  model: string
  cost: string
}

interface BackendAITaskRow {
  id: string
  name?: string
  type?: string
  status: string
  provider?: string
  model?: string
  cost?: number | string
}

export async function listAITasks() {
  const response = (await apiClient.get<BackendAITaskRow[]>('/ai/tasks')) as ApiEnvelope<BackendAITaskRow[]>
  return {
    ...response,
    data: response.data.map((task) => ({
      id: task.id,
      name: task.name ?? task.type ?? task.id,
      status: task.status,
      provider: task.provider ?? 'n/a',
      model: task.model ?? 'n/a',
      cost: typeof task.cost === 'number' ? `$${task.cost.toFixed(2)}` : (task.cost ?? '$0.00'),
    })),
  } satisfies ApiEnvelope<AITaskRow[]>
}
