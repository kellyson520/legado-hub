import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface WorkSnapshot {
  published_claims: Array<{ id: string; subject_entity_id: string; predicate: string; evidence_ids: string[] }>
  candidate_claims?: Array<{ id: string; subject_entity_id: string; predicate: string; evidence_ids: string[] }>
  open_conflicts: Array<{ id: string; incumbent_claim_id: string; conflicting_claim_id: string }>
}

export interface EvidenceCitation { excerpt: string; canonical_chapter_title: string; content_sha256: string }

export interface AnalysisTask {
  id: string
  work_id?: string
  status: 'queued' | 'running' | 'paused' | 'blocked' | 'completed' | string
  tool_call_count: number
  policy: { max_tool_calls_per_task?: number; max_tokens_per_task?: number }
  checkpoint: {
    selected_evidence_ids?: string[]
    token_count?: number
    blocked_reason?: string
    completion_reasons?: string[]
    outcomes?: Array<{ claim_id: string; verdict: string; claim_status: string; reasons: string[] }>
  }
}

export function getWorkSnapshot(workId: string): Promise<ApiEnvelope<WorkSnapshot>> {
  return apiClient.get<WorkSnapshot>(`/novel-analysis/works/${workId}/snapshot`)
}

export function getEvidence(evidenceId: string): Promise<ApiEnvelope<EvidenceCitation>> {
  return apiClient.get<EvidenceCitation>(`/novel-analysis/evidence/${evidenceId}`)
}

export function getWorkTasks(workId: string): Promise<ApiEnvelope<{ items: AnalysisTask[] }>> {
  return apiClient.get<{ items: AnalysisTask[] }>(`/novel-analysis/works/${workId}/tasks`)
}

export function pauseAnalysisTask(taskId: string): Promise<ApiEnvelope<AnalysisTask>> {
  return apiClient.post<AnalysisTask>(`/novel-analysis/tasks/${taskId}/pause`)
}

export function resumeAnalysisTask(taskId: string): Promise<ApiEnvelope<AnalysisTask>> {
  return apiClient.post<AnalysisTask>(`/novel-analysis/tasks/${taskId}/resume`)
}

export function runAnalysisTask(taskId: string): Promise<ApiEnvelope<AnalysisTask>> {
  return apiClient.post<AnalysisTask>(`/novel-analysis/tasks/${taskId}/run`)
}
