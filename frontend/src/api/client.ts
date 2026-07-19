import axios, {
  AxiosError,
  AxiosHeaders,
  type AxiosAdapter,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

import type { ApiEnvelope, AuthSession } from './types'

type RetryableConfig = InternalAxiosRequestConfig & { _retry?: boolean; skipAuthRefresh?: boolean }

export type ApiRequestConfig = AxiosRequestConfig & { skipAuthRefresh?: boolean }

export interface AuthFailureOptions {
  clearStoredToken?: boolean
}

export interface CreateApiClientOptions {
  adapter?: AxiosAdapter
  baseURL?: string
  getAccessToken?: () => string | null
  onRefresh?: () => Promise<AuthSession | null>
  onAuthFailure?: (options?: AuthFailureOptions) => void
}

export interface AuthClientBinding {
  getAccessToken: () => string | null
  refresh: () => Promise<AuthSession | null>
  onAuthFailure: (options?: AuthFailureOptions) => void
}

let authBinding: AuthClientBinding | null = null

export function configureAuthClient(binding: AuthClientBinding | null) {
  authBinding = binding
}

export function getConfiguredAccessToken() {
  return authBinding?.getAccessToken() ?? null
}

function applyAuthorization(config: RetryableConfig, token: string) {
  if (config.headers instanceof AxiosHeaders) {
    config.headers.set('Authorization', `Bearer ${token}`)
    return
  }

  const headers = AxiosHeaders.from(config.headers)
  headers.set('Authorization', `Bearer ${token}`)
  config.headers = headers
}

function unwrapResponse<T>(response: { data: ApiEnvelope<T> }) {
  return response.data
}

function resolveRequestUrl(baseURL: string, url: string) {
  if (/^https?:\/\//i.test(url)) return url
  const base = baseURL.replace(/\/$/, '')
  if (!base || base === '/') return url
  if (url === base || url.startsWith(`${base}/`)) return url
  return `${base}/${url.replace(/^\//, '')}`
}

export function createApiClient(options: CreateApiClientOptions = {}) {
  const instance: AxiosInstance = axios.create({
    baseURL: options.baseURL ?? '/',
    timeout: 60_000,
    adapter: options.adapter,
    headers: {
      'Content-Type': 'application/json',
    },
  })

  instance.interceptors.request.use((config) => {
    const token = options.getAccessToken?.()
    if (token) {
      applyAuthorization(config as RetryableConfig, token)
    }
    return config
  })

  instance.interceptors.response.use(
    (response) => response,
    async (error: AxiosError<ApiEnvelope<unknown>>) => {
      const config = error.config as RetryableConfig | undefined
      if (!config) {
        return Promise.reject(error)
      }

      if (error.response?.status === 401) {
        if (config._retry) {
          options.onAuthFailure?.({ clearStoredToken: true })
          return Promise.reject(error)
        }
        if (config.skipAuthRefresh || config.url?.includes('/auth/refresh') || !options.onRefresh) {
          return Promise.reject(error)
        }
        config._retry = true
        const session = await options.onRefresh()
        if (session?.accessToken) {
          applyAuthorization(config, session.accessToken)
          return instance.request(config)
        }
        options.onAuthFailure?.()
      }

      return Promise.reject(error)
    }
  )

  return {
    raw: instance,
    get: async <T>(url: string, config?: ApiRequestConfig) =>
      unwrapResponse<T>(await instance.get<ApiEnvelope<T>>(url, config)),
    post: async <T>(url: string, data?: unknown, config?: ApiRequestConfig) =>
      unwrapResponse<T>(await instance.post<ApiEnvelope<T>>(url, data, config)),
    put: async <T>(url: string, data?: unknown, config?: ApiRequestConfig) =>
      unwrapResponse<T>(await instance.put<ApiEnvelope<T>>(url, data, config)),
    patch: async <T>(url: string, data?: unknown, config?: ApiRequestConfig) =>
      unwrapResponse<T>(await instance.patch<ApiEnvelope<T>>(url, data, config)),
    delete: async <T>(url: string, config?: ApiRequestConfig) =>
      unwrapResponse<T>(await instance.delete<ApiEnvelope<T>>(url, config)),
    stream: async (url: string, init: RequestInit = {}) => {
      const requestUrl = resolveRequestUrl(options.baseURL ?? '/', url)
      const headers = new Headers(init.headers)
      const token = options.getAccessToken?.()
      if (token) headers.set('Authorization', `Bearer ${token}`)

      let response = await fetch(requestUrl, { ...init, headers })
      if (response.status === 401 && options.onRefresh) {
        const session = await options.onRefresh()
        if (session?.accessToken) {
          headers.set('Authorization', `Bearer ${session.accessToken}`)
          response = await fetch(requestUrl, { ...init, headers })
          if (response.status === 401) options.onAuthFailure?.({ clearStoredToken: true })
        } else {
          options.onAuthFailure?.()
        }
      }
      return response
    },
  }
}

export const apiClient = createApiClient({
  baseURL: '/api',
  getAccessToken: () => authBinding?.getAccessToken() ?? null,
  onRefresh: () => authBinding?.refresh() ?? Promise.resolve(null),
  onAuthFailure: (options) => authBinding?.onAuthFailure(options),
})
