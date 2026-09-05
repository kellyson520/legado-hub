import type { ReactNode } from 'react'

import { useLanguage } from '@/app/providers/LanguageProvider'
import { ListStatus } from '@/components/data/ListStatus'
import { PaginationToolbar } from '@/components/data/PaginationToolbar'
import type { UseServerPaginationResult } from '@/hooks/useServerPagination'
import { cn } from '@/lib/utils'

export type PaginatedListPagination = Pick<
  UseServerPaginationResult<unknown>,
  | 'meta'
  | 'searchInput'
  | 'appliedSearch'
  | 'loading'
  | 'error'
  | 'setSearchInput'
  | 'submitSearch'
  | 'clearSearch'
  | 'goToPage'
  | 'retry'
>

export interface PaginatedListControlsProps {
  pagination: PaginatedListPagination
  empty: boolean
  loadingLabel: string
  errorLabel: string
  emptyLabel: string
  searchLabel?: string
  itemLabel?: string
  showSearch?: boolean
  className?: string
  children?: ReactNode
}

export function PaginatedListControls({
  pagination,
  empty,
  loadingLabel,
  errorLabel,
  emptyLabel,
  searchLabel,
  itemLabel,
  showSearch,
  className,
  children,
}: PaginatedListControlsProps) {
  const { t } = useLanguage()
  return (
    <div className={cn('space-y-3', className)}>
      <PaginationToolbar
        page={pagination.meta.page}
        totalPages={pagination.meta.total_pages}
        total={pagination.meta.total}
        searchInput={pagination.searchInput}
        appliedSearch={pagination.appliedSearch}
        loading={pagination.loading}
        showSearch={showSearch}
        searchLabel={searchLabel ? t(searchLabel) : undefined}
        itemLabel={itemLabel ? t(itemLabel) : undefined}
        showLoadingLabel={false}
        showEmptyLabel={false}
        onSearchInput={pagination.setSearchInput}
        onSearch={() => pagination.submitSearch()}
        onClearSearch={pagination.clearSearch}
        onPageChange={pagination.goToPage}
      />
      <ListStatus
        loading={pagination.loading}
        error={pagination.error}
        empty={empty}
        onRetry={pagination.retry}
        loadingLabel={t(loadingLabel)}
        errorLabel={t(errorLabel)}
        emptyLabel={t(emptyLabel)}
      />
      {children}
    </div>
  )
}
