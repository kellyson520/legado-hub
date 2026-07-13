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

export async function listUsers() {
  return apiClient.get<AdminUserRow[]>('/admin/users') as Promise<ApiEnvelope<AdminUserRow[]>>
}

export async function listAuditLogs() {
  return apiClient.get<AuditLogRow[]>('/admin/audit') as Promise<ApiEnvelope<AuditLogRow[]>>
}

export async function createUser(payload: { username: string; display_name: string; role: 'admin' | 'user'; password: string }) { return apiClient.post<AdminUserRow>('/admin/users', payload) }
export async function updateUser(id: string, payload: Partial<Pick<AdminUserRow, 'display_name' | 'role'>>) { return apiClient.raw.patch(`/admin/users/${id}`, payload) }
export async function setUserEnabled(id: string, enabled: boolean) { return apiClient.post<AdminUserRow>(`/admin/users/${id}/${enabled ? 'enable' : 'disable'}`) }
export async function resetUserPassword(id: string, password: string) { return apiClient.post<{ user_id: string }>(`/admin/users/${id}/reset-password`, { password }) }
