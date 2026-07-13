export interface ApiEnvelope<T> {
  success: boolean
  code: string
  message: string
  data: T
  meta: Record<string, unknown>
  trace_id: string | null
}

export interface AuthUser {
  id: string
  username: string
  displayName?: string
  roles?: string[]
  permissions: string[]
}

export interface AuthSession {
  accessToken: string
  refreshToken: string
  user: AuthUser
}
