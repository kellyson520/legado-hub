export interface ApiEnvelope<T> {
  success: boolean
  code: string
  message: string
  data: T
  meta: Record<string, unknown>
  trace_id: string | null
}

export interface PaginatedMeta {
  page: number
  page_size: number
  total: number
  total_pages: number
  search?: string
}

export interface PaginatedQueryParams {
  page?: number
  page_size?: number
  search?: string
}

export interface PaginatedStatusQueryParams extends PaginatedQueryParams {
  status?: string
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
