import type { PaginatedMeta } from '@/api/types'

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
  const normalized: PaginatedMeta = {
    page,
    page_size: pageSize,
    total,
    total_pages: totalPages,
    search: typeof meta.search === 'string' ? meta.search : undefined,
  }
  if (meta.status_counts && typeof meta.status_counts === 'object' && !Array.isArray(meta.status_counts)) {
    const counts = Object.fromEntries(
      Object.entries(meta.status_counts).filter(([, value]) => typeof value === 'number' && Number.isFinite(value)),
    ) as Record<string, number>
    normalized.status_counts = counts
  }
  return normalized
}
