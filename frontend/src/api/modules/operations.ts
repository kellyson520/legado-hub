import { apiClient, getConfiguredAccessToken } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface OperationJobRow {
  id: string
  kind: string
  status: string
  tenant_id?: string
  tenantId?: string
  attempt_count?: number
  attemptCount?: number
  created_at?: string
  createdAt?: string
  last_error?: string | null
  lastError?: string | null
}

export interface OperationDeliveryRow {
  event_id?: string
  eventId?: string
  event_type?: string
  eventType?: string
  tenant_id?: string
  tenantId?: string
  target_url?: string
  targetUrl?: string
  dedupe_key?: string | null
  dedupeKey?: string | null
  status: string
  attempt_count?: number
  attemptCount?: number
  last_error?: string | null
  lastError?: string | null
  next_attempt_at?: string | null
  nextAttemptAt?: string | null
  delivered_at?: string | null
  deliveredAt?: string | null
  created_at?: string | null
  createdAt?: string | null
}

export interface OperationDeliveryAttemptRow {
  id: number
  event_id?: string
  eventId?: string
  attempt_no?: number
  attemptNo?: number
  delivered: boolean
  status_code?: number | null
  statusCode?: number | null
  error_message?: string | null
  errorMessage?: string | null
  created_at?: string | null
  createdAt?: string | null
}

export interface OperationSourceBuildRow {
  id: string
  source_definition_id?: number
  sourceDefinitionId?: number
  source_type?: string
  sourceType?: string
  source_id?: string
  sourceId?: string
  status: string
  payload: {
    canonical_url?: string
    keyword?: string
    submitted_by?: string
    [key: string]: unknown
  }
  created_by?: string
  createdBy?: string
  created_at?: string | null
  createdAt?: string | null
  latest_run?: {
    id: string
    trigger: string
    score: number
    grade: string
    created_at?: string | null
    createdAt?: string | null
  } | null
  latestRun?: {
    id: string
    trigger: string
    score: number
    grade: string
    created_at?: string | null
    createdAt?: string | null
  } | null
}

export interface OperationReviewQueueRow {
  id: string
  item_type?: string
  itemType?: string
  work_id?: string
  workId?: string
  source_chapter_id?: string
  sourceChapterId?: string
  proposal_type?: string
  proposalType?: string
  summary?: string
  subject?: string
  relation?: string
  object_name?: string
  objectName?: string
  evidence: string
  payload?: Record<string, unknown>
  status: string
  created_by?: string
  createdBy?: string
  reviewed_by?: string | null
  reviewedBy?: string | null
  created_at?: string | null
  createdAt?: string | null
  published_at?: string | null
  publishedAt?: string | null
}

export interface OperationAgentToolResultRow {
  id?: string
  status: string
  data?: Record<string, unknown>
  error_code?: string | null
  errorCode?: string | null
  created_at?: string | null
  createdAt?: string | null
}

export interface OperationAgentToolEvidenceRow {
  id: string
  evidence_type?: string
  evidenceType?: string
  resource_id?: string
  resourceId?: string
  payload?: Record<string, unknown>
  created_at?: string | null
  createdAt?: string | null
}

export interface OperationAgentToolInvocationRow {
  id: string
  tool_name?: string
  toolName?: string
  category: string
  arguments?: Record<string, unknown>
  created_at?: string | null
  createdAt?: string | null
  result?: OperationAgentToolResultRow | null
  evidence?: OperationAgentToolEvidenceRow[]
}

export interface OperationAgentRunRow {
  id: string
  tenant_id?: string
  tenantId?: string
  agent_kind?: string
  agentKind?: string
  input_payload?: Record<string, unknown>
  inputPayload?: Record<string, unknown>
  status: string
  created_at?: string | null
  createdAt?: string | null
  tool_invocation_count?: number
  toolInvocationCount?: number
  accepted_count?: number
  acceptedCount?: number
  rejected_count?: number
  rejectedCount?: number
  evidence_count?: number
  evidenceCount?: number
  latest_tool_name?: string | null
  latestToolName?: string | null
}

export interface OperationAgentRunDetail extends OperationAgentRunRow {
  tool_history?: OperationAgentToolInvocationRow[]
  toolHistory?: OperationAgentToolInvocationRow[]
}

export interface OperationStreamEvent<T = Record<string, unknown>> {
  id?: string
  event: string
  data: T
}

export interface OperationReviewResolveResult {
  queueItemId: string
  queue_item_id?: string
  resultId: string
  result_id?: string
  itemType: string
  item_type?: string
  status: string
  action: string
  reviewedBy?: string | null
  reviewed_by?: string | null
  publishedAt?: string | null
  published_at?: string | null
  resolvedAt?: string | null
  resolved_at?: string | null
}

export function listOperationsJobs(): Promise<ApiEnvelope<OperationJobRow[]>> {
  return apiClient.get<OperationJobRow[]>('/events/jobs')
}

export function listEventDeliveries(): Promise<ApiEnvelope<OperationDeliveryRow[]>> {
  return apiClient.get<OperationDeliveryRow[]>('/events/deliveries')
}

export function listEventDeliveryAttempts(eventId: string): Promise<ApiEnvelope<OperationDeliveryAttemptRow[]>> {
  return apiClient.get<OperationDeliveryAttemptRow[]>(`/events/deliveries/${eventId}/attempts`)
}

export function listSourceBuildCandidates(): Promise<ApiEnvelope<OperationSourceBuildRow[]>> {
  return apiClient.get<OperationSourceBuildRow[]>('/events/source-builds')
}

export function listOperationAgentRuns(): Promise<ApiEnvelope<OperationAgentRunRow[]>> {
  return apiClient.get<OperationAgentRunRow[]>('/events/agent-runs')
}

export function getOperationAgentRun(runId: string): Promise<ApiEnvelope<OperationAgentRunDetail>> {
  return apiClient.get<OperationAgentRunDetail>(`/events/agent-runs/${runId}`)
}

export function listReviewQueueCandidates(): Promise<ApiEnvelope<OperationReviewQueueRow[]>> {
  return apiClient.get<OperationReviewQueueRow[]>('/events/review-queue')
}

export function resolveReviewQueueItem(
  itemId: string,
  payload: {
    itemType: string
    action?: string
    memoryNote?: Record<string, unknown>
  }
): Promise<ApiEnvelope<OperationReviewResolveResult>> {
  return apiClient.post<OperationReviewResolveResult>(`/events/review-queue/${itemId}/resolve`, {
    item_type: payload.itemType,
    action: payload.action ?? 'publish',
    memory_note: payload.memoryNote,
  })
}

export async function subscribeOperationEvents({
  tenantId,
  limit = 20,
  once = false,
  onEvent,
  onDisconnect,
}: {
  tenantId?: string
  limit?: number
  once?: boolean
  onEvent: (event: OperationStreamEvent) => void
  onDisconnect?: () => void
}) {
  const token = getConfiguredAccessToken()
  const controller = new AbortController()
  const params = new URLSearchParams()
  if (tenantId) params.set('tenant_id', tenantId)
  params.set('limit', String(limit))
  if (once) params.set('once', 'true')

  const response = await fetch(`/api/events/stream?${params.toString()}`, {
    method: 'GET',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal: controller.signal,
  })

  if (!response.ok) {
    throw new Error(`Failed to subscribe operation events: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    return () => controller.abort()
  }

  const decoder = new TextDecoder()
  let buffer = ''

  const consume = async () => {
    while (!controller.signal.aborted) {
      const { done, value } = await reader.read()
      if (done) {
        if (!controller.signal.aborted) onDisconnect?.()
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''
      for (const frame of frames) {
        const parsed = parseSseFrame(frame)
        if (parsed) onEvent(parsed)
      }
    }
  }

  void consume().catch(() => {
    if (!controller.signal.aborted) onDisconnect?.()
    controller.abort()
  })
  return () => controller.abort()
}

function parseSseFrame(frame: string): OperationStreamEvent | null {
  const parsed: OperationStreamEvent = { event: 'message', data: {} }
  for (const rawLine of frame.split('\n')) {
    const line = rawLine.trim()
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('id:')) {
      parsed.id = line.slice(3).trim()
      continue
    }
    if (line.startsWith('event:')) {
      parsed.event = line.slice(6).trim()
      continue
    }
    if (line.startsWith('data:')) {
      try {
        parsed.data = JSON.parse(line.slice(5).trim()) as Record<string, unknown>
      } catch {
        parsed.data = {}
      }
    }
  }
  return parsed
}
