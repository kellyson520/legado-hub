import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface WorkSnapshot {
  published_claims: Array<{ id: string; subject_entity_id: string; predicate: string; evidence_ids: string[] }>
  open_conflicts: Array<{ id: string; incumbent_claim_id: string; conflicting_claim_id: string }>
}

export interface EvidenceCitation { excerpt: string; canonical_chapter_title: string; content_sha256: string }

export function getWorkSnapshot(workId: string): Promise<ApiEnvelope<WorkSnapshot>> {
  return apiClient.get<WorkSnapshot>(`/novel-analysis/works/${workId}/snapshot`)
}

export function getEvidence(evidenceId: string): Promise<ApiEnvelope<EvidenceCitation>> {
  return apiClient.get<EvidenceCitation>(`/novel-analysis/evidence/${evidenceId}`)
}
