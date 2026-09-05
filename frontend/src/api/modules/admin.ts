import { apiClient } from '@/api/client'
import type { PaginatedEnvelope, PaginatedStatusQueryParams } from '@/api/types'

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

export interface AdminListParams extends PaginatedStatusQueryParams {}

export async function listUsers(params: AdminListParams = {}): Promise<PaginatedEnvelope<AdminUserRow>> {
  return apiClient.get<AdminUserRow[]>('/admin/users', { params })
}

export async function listAuditLogs(params: AdminListParams = {}): Promise<PaginatedEnvelope<AuditLogRow>> {
  return apiClient.get<AuditLogRow[]>('/admin/audit', { params })
}

export async function createUser(payload: { username: string; display_name: string; role: 'admin' | 'user'; password: string }) { return apiClient.post<AdminUserRow>('/admin/users', payload) }
export async function updateUser(id: string, payload: Partial<Pick<AdminUserRow, 'display_name' | 'role'>>) {
  return apiClient.patch<AdminUserRow>(`/admin/users/${id}`, payload)
}
export async function setUserEnabled(id: string, enabled: boolean) { return apiClient.post<AdminUserRow>(`/admin/users/${id}/${enabled ? 'enable' : 'disable'}`) }
export async function resetUserPassword(id: string, password: string) { return apiClient.post<{ user_id: string }>(`/admin/users/${id}/reset-password`, { password }) }
export async function revokeUserSessions(id: string) { return apiClient.post<{ user_id: string }>(`/admin/sessions/${id}/revoke`) }
export function listApiKeys(params: AdminListParams = {}): Promise<PaginatedEnvelope<ApiKeyRow>> { return apiClient.get<ApiKeyRow[]>('/admin/api-keys', { params }) }
export function createApiKey(payload: { name: string; permissions: string[] }) { return apiClient.post<ApiKeyRow>('/admin/api-keys', payload) }
export function disableApiKey(id: number) { return apiClient.patch<{ api_key_id: number }>(`/admin/api-keys/${id}/disable`) }
export function deleteApiKey(id: number) { return apiClient.delete<{ api_key_id: number }>(`/admin/api-keys/${id}`) }
