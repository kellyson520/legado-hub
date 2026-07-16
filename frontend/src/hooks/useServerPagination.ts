import { useCallback, useEffect, useRef, useState } from 'react'

import type { ApiEnvelope, PaginatedMeta } from '@/api/types'
import { normalizePageMeta } from '@/lib/pagination'

export interface ServerPageRequest {
  page: number
  pageSize: number
  search: string
}

export interface UseServerPaginationOptions<T> {
  pageSize: number
  load: (request: ServerPageRequest) => Promise<ApiEnvelope<T[]>>
  initialSearch?: string
}

export interface UseServerPaginationResult<T> {
  rows: T[]
  meta: PaginatedMeta
  searchInput: string
  appliedSearch: string
  loading: boolean
  error: Error | null
  setSearchInput: (value: string) => void
  submitSearch: (value?: string) => void
  clearSearch: () => void
  goToPage: (page: number) => void
  retry: () => void
  reload: () => void
}

interface PageTarget {
  page: number
  search: string
}

export function useServerPagination<T>(
  options: UseServerPaginationOptions<T>,
): UseServerPaginationResult<T> {
  const loadRef = useRef(options.load)
  const pageSizeRef = useRef(options.pageSize)
  const initialSearchRef = useRef(options.initialSearch?.trim() ?? '')
  const mountedRef = useRef(true)
  const requestIdRef = useRef(0)
  const appliedSearchRef = useRef(initialSearchRef.current)
  const metaRef = useRef<PaginatedMeta>(normalizePageMeta({}, 1, options.pageSize, 0))
  const retryTargetRef = useRef<PageTarget>({ page: 1, search: initialSearchRef.current })
  const successfulTargetRef = useRef<PageTarget>({ page: 1, search: initialSearchRef.current })
  const [rows, setRows] = useState<T[]>([])
  const [meta, setMeta] = useState<PaginatedMeta>(metaRef.current)
  const [searchInput, setSearchInput] = useState(initialSearchRef.current)
  const [appliedSearch, setAppliedSearch] = useState(initialSearchRef.current)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  loadRef.current = options.load
  pageSizeRef.current = options.pageSize

  const requestPage = useCallback(async (requestedPage: number, requestedSearch: string) => {
    if (!mountedRef.current) return
    const search = requestedSearch.trim()
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    retryTargetRef.current = { page: requestedPage, search }
    setLoading(true)
    setError(null)
    try {
      const response = await loadRef.current({
        page: requestedPage,
        pageSize: pageSizeRef.current,
        search,
      })
      if (!mountedRef.current || requestIdRef.current !== requestId) return
      const nextMeta = normalizePageMeta(response.meta, requestedPage, pageSizeRef.current, response.data.length)
      const normalizedMeta = { ...nextMeta, search }
      setRows(response.data)
      setMeta(normalizedMeta)
      metaRef.current = normalizedMeta
      setAppliedSearch(search)
      appliedSearchRef.current = search
      successfulTargetRef.current = { page: normalizedMeta.page, search }
    } catch (caught) {
      if (!mountedRef.current || requestIdRef.current !== requestId) return
      setError(caught instanceof Error ? caught : new Error('Failed to load paginated data'))
    } finally {
      if (mountedRef.current && requestIdRef.current === requestId) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    void requestPage(1, initialSearchRef.current)
    return () => {
      mountedRef.current = false
      requestIdRef.current += 1
    }
  }, [requestPage])

  const submitSearch = useCallback((value = searchInput) => {
    const search = value.trim()
    setSearchInput(value)
    setAppliedSearch(search)
    appliedSearchRef.current = search
    void requestPage(1, search)
  }, [requestPage, searchInput])

  const clearSearch = useCallback(() => {
    setSearchInput('')
    setAppliedSearch('')
    appliedSearchRef.current = ''
    void requestPage(1, '')
  }, [requestPage])

  const goToPage = useCallback((nextPage: number) => {
    const currentMeta = metaRef.current
    if (nextPage < 1 || nextPage > currentMeta.total_pages || nextPage === currentMeta.page) return
    void requestPage(nextPage, appliedSearchRef.current)
  }, [requestPage])

  const retry = useCallback(() => {
    const target = retryTargetRef.current
    void requestPage(target.page, target.search)
  }, [requestPage])

  const reload = useCallback(() => {
    const target = successfulTargetRef.current
    void requestPage(target.page, target.search)
  }, [requestPage])

  return {
    rows,
    meta,
    searchInput,
    appliedSearch,
    loading,
    error,
    setSearchInput,
    submitSearch,
    clearSearch,
    goToPage,
    retry,
    reload,
  }
}
