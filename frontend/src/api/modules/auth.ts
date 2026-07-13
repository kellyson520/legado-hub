import { apiClient } from '@/api/client'
import type { AuthSession } from '@/api/types'

export interface LoginPayload {
  username: string
  password: string
}

export interface AuthTokens {
  access_token: string
  refresh_token?: string
  permissions?: string[]
  roles?: string[]
  display_name?: string
}

export interface CurrentIdentity {
  user_id: number
  permissions: string[]
  roles?: string[]
  display_name?: string
  session_id?: string | null
}

export function createAuthSession(tokens: AuthTokens, identity: CurrentIdentity, username: string, previousRefreshToken?: string): AuthSession {
  const refreshToken = tokens.refresh_token ?? previousRefreshToken
  if (!refreshToken) throw new Error('Missing refresh token')
  const user = {
    id: String(identity.user_id),
    username,
    permissions: identity.permissions,
    ...(identity.display_name ? { displayName: identity.display_name } : {}),
    ...(identity.roles ? { roles: identity.roles } : {}),
  }
  return {
    accessToken: tokens.access_token,
    refreshToken,
    user,
  }
}

export async function login(payload: LoginPayload) {
  const response = await apiClient.post<AuthTokens>('/auth/login', payload)
  return response.data
}

export async function refreshSession(refreshToken: string) {
  const response = await apiClient.post<AuthTokens>('/auth/refresh', { refresh_token: refreshToken })
  return response.data
}

export async function logout() {
  return apiClient.post<null>('/auth/logout')
}

export async function getCurrentUser() {
  const response = await apiClient.get<CurrentIdentity>('/auth/me')
  return response.data
}
