import axios, {
  AxiosError,
  AxiosHeaders,
  type AxiosAdapter,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

import type { ApiEnvelope, AuthSession } from './types'

type RetryableConfig = InternalAxiosRequestConfig & { _retry?: boolean }

export interface CreateApiClientOptions {
  adapter?: AxiosAdapter
  baseURL?: string
  getAccessToken?: () => string | null
  onRefresh?: () => Promise<AuthSession | null>
  onAuthFailure?: () => void
}

export interface AuthClientBinding {
  getAccessToken: () => string | null
  refresh: () => Promise<AuthSession | null>
  onAuthFailure: () => void
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

      if (error.response?.status === 401 && !config._retry && !config.url?.includes('/auth/refresh') && options.onRefresh) {
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
    get: async <T>(url: string, config?: AxiosRequestConfig) =>
      unwrapResponse<T>(await instance.get<ApiEnvelope<T>>(url, config)),
    post: async <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
      unwrapResponse<T>(await instance.post<ApiEnvelope<T>>(url, data, config)),
    put: async <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
      unwrapResponse<T>(await instance.put<ApiEnvelope<T>>(url, data, config)),
    patch: async <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
      unwrapResponse<T>(await instance.patch<ApiEnvelope<T>>(url, data, config)),
    delete: async <T>(url: string, config?: AxiosRequestConfig) =>
      unwrapResponse<T>(await instance.delete<ApiEnvelope<T>>(url, config)),
  }
}

export const apiClient = createApiClient({
  baseURL: '/api',
  getAccessToken: () => authBinding?.getAccessToken() ?? null,
  onRefresh: () => authBinding?.refresh() ?? Promise.resolve(null),
  onAuthFailure: () => authBinding?.onAuthFailure(),
})
