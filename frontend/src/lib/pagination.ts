import type { PaginatedMeta, PaginatedQueryParams } from '@/api/types'

export interface PaginatedRequest {
  page: number
  pageSize: number
  search: string
}

export function toPaginatedQueryParams(request: PaginatedRequest): PaginatedQueryParams {
  return {
    page: request.page,
    page_size: request.pageSize,
    search: request.search,
  }
}

function integerAtLeast(value: unknown, fallback: number, minimum: number) {
  return typeof value === 'number' && Number.isInteger(value) && value >= minimum
    ? value
    : fallback
}

export function normalizePageMeta(
  meta: Record<string, unknown>,
  requestedPage: number,
  defaultPageSize: number,
  rowCount: number,
): PaginatedMeta {
  const safePage = integerAtLeast(requestedPage, 1, 1)
  const safePageSize = integerAtLeast(defaultPageSize, 20, 1)
  const safeRowCount = integerAtLeast(rowCount, 0, 0)
  const pageSize = integerAtLeast(meta.page_size, safePageSize, 1)
  const total = integerAtLeast(meta.total, safeRowCount, 0)
  const page = integerAtLeast(meta.page, safePage, 1)
  const calculatedPages = total > 0 ? Math.ceil(total / pageSize) : 1
  const totalPages = integerAtLeast(meta.total_pages, calculatedPages, 1)
  return {
    page,
    page_size: pageSize,
    total,
    total_pages: totalPages,
    search: typeof meta.search === 'string' ? meta.search : undefined,
  }
}
