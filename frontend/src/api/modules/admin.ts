import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface AdminUserRow {
  id: string
  username: string
  display_name: string
  role: 'admin' | 'user'
  roles: string[]
  status: 'enabled' | 'disabled'
  created_at?: string | null
  last_login_at?: string | null
}

export interface AuditLogRow {
  id: string
  action: string
  resource: string
  detail: string
  createdAt?: string
}
export interface ApiKeyRow { id: number; name: string; permissions: string[]; is_enabled: boolean; raw_key?: string }

export interface AdminListParams {
  page?: number
  page_size?: number
  search?: string
  status?: string
}

export async function listUsers(params: AdminListParams = {}) {
  return apiClient.get<AdminUserRow[]>('/admin/users', { params }) as Promise<ApiEnvelope<AdminUserRow[]>>
}

export async function listAuditLogs(params: AdminListParams = {}) {
  return apiClient.get<AuditLogRow[]>('/admin/audit', { params }) as Promise<ApiEnvelope<AuditLogRow[]>>
}

export async function createUser(payload: { username: string; display_name: string; role: 'admin' | 'user'; password: string }) { return apiClient.post<AdminUserRow>('/admin/users', payload) }
export async function updateUser(id: string, payload: Partial<Pick<AdminUserRow, 'display_name' | 'role'>>) {
  return (await apiClient.raw.patch<ApiEnvelope<AdminUserRow>>(`/admin/users/${id}`, payload)).data
}
export async function setUserEnabled(id: string, enabled: boolean) { return apiClient.post<AdminUserRow>(`/admin/users/${id}/${enabled ? 'enable' : 'disable'}`) }
export async function resetUserPassword(id: string, password: string) { return apiClient.post<{ user_id: string }>(`/admin/users/${id}/reset-password`, { password }) }
export async function revokeUserSessions(id: string) { return apiClient.post<{ user_id: string }>(`/admin/sessions/${id}/revoke`) }
export function listApiKeys(params: AdminListParams = {}) { return apiClient.get<ApiKeyRow[]>('/admin/api-keys', { params }) as Promise<ApiEnvelope<ApiKeyRow[]>> }
export function createApiKey(payload: { name: string; permissions: string[] }) { return apiClient.post<ApiKeyRow>('/admin/api-keys', payload) }
export function disableApiKey(id: number) { return apiClient.raw.patch<ApiEnvelope<{ api_key_id: number }>>(`/admin/api-keys/${id}/disable`).then((r) => r.data) }
export function deleteApiKey(id: number) { return apiClient.raw.delete<ApiEnvelope<{ api_key_id: number }>>(`/admin/api-keys/${id}`).then((r) => r.data) }
