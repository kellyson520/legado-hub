import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.message)
    return Promise.reject(error)
  }
)

export interface ApiResponse<T = any> {
  success: boolean
  code?: string
  message?: string
  data?: T
  total?: number
  page?: number
  pageSize?: number
}

// ==================== 仪表盘 ====================
export const dashboardApi = {
  getStats: () => api.get<ApiResponse>('/dashboard/stats').then(r => r.data),
  getGroups: () => api.get<ApiResponse>('/dashboard/groups').then(r => r.data),
}

// ==================== 书源管理 ====================
export interface BookSource {
  bookSourceUrl: string
  bookSourceName: string
  bookSourceGroup?: string
  bookSourceType?: number
  bookSourceComment?: string
  enabled?: boolean
  status?: string
  lastUpdateTime?: number
  searchUrl?: string
  ruleSearch?: string
  ruleToc?: string
  ruleContent?: string
  ruleBookInfo?: string
  [key: string]: any
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

export const sourcesApi = {
  listBookSources: (params: {
    page?: number
    pageSize?: number
    search?: string
    group?: string
    status?: string
    enabledOnly?: boolean
  } = {}) =>
    api
      .get<ApiResponse>('/sources/book', { params })
      .then((r) => r.data),

  getBookSource: (url: string) =>
    api.get<ApiResponse>(`/sources/book/${encodeURIComponent(url)}`).then(r => r.data),

  createBookSource: (source: any) =>
    api.post<ApiResponse>('/sources/book', source).then(r => r.data),

  updateBookSource: (url: string, source: any) =>
    api.put<ApiResponse>(`/sources/book/${encodeURIComponent(url)}`, source).then(r => r.data),

  deleteBookSource: (url: string) =>
    api.delete<ApiResponse>(`/sources/book/${encodeURIComponent(url)}`).then(r => r.data),

  importBookSources: (sources: any[]) =>
    api.post<ApiResponse>('/sources/book/import', sources).then(r => r.data),
}

// ==================== 书源测试 ====================
export const testApi = {
  search: (sourceUrl: string, keyword: string, timeout = 30) =>
    api
      .post<ApiResponse>('/test/search', { sourceUrl, keyword, timeout })
      .then((r) => r.data),

  toc: (sourceUrl: string, bookUrl: string, timeout = 30) =>
    api
      .post<ApiResponse>('/test/toc', { sourceUrl, bookUrl, timeout })
      .then((r) => r.data),

  content: (sourceUrl: string, chapterUrl: string, timeout = 30) =>
    api
      .post<ApiResponse>('/test/content', { sourceUrl, chapterUrl, timeout })
      .then((r) => r.data),

  full: (sourceUrl: string, keyword = '斗罗大陆', timeout = 30) =>
    api
      .post<ApiResponse>('/test/full', { sourceUrl, keyword, timeout })
      .then((r) => r.data),
}

// ==================== 健康检查 ====================
export const healthApi = {
  checkAll: (sourceType?: string, limit = 50) =>
    api
      .get<ApiResponse>('/health/check', { params: { sourceType, limit } })
      .then((r) => r.data),

  checkSingle: (sourceType: string, url: string) =>
    api
      .get<ApiResponse>(`/health/check/${sourceType}/${encodeURIComponent(url)}`)
      .then((r) => r.data),
}

// ==================== 输出/导出 ====================
export const outputApi = {
  getBookSources: (group?: string, enabledOnly = true) =>
    api
      .get<ApiResponse>('/output/book', { params: { group, enabledOnly } })
      .then((r) => r.data),

  exportJson: (enabledOnly = true) =>
    api.get('/output/export.json', { params: { enabledOnly }, responseType: 'blob' }),
}

export default api
