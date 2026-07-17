import { useId } from 'react'
import type { FormEvent } from 'react'

import { useLanguage } from '@/app/providers/LanguageProvider'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export interface PaginationToolbarProps {
  page: number
  totalPages: number
  total: number
  searchInput: string
  appliedSearch: string
  loading: boolean
  showSearch?: boolean
  searchLabel?: string
  itemLabel?: string
  emptyLabel?: string
  showLoadingLabel?: boolean
  showEmptyLabel?: boolean
  onSearchInput: (value: string) => void
  onSearch: () => void
  onClearSearch: () => void
  onPageChange: (page: number) => void
}

export function PaginationToolbar({
  page,
  totalPages,
  total,
  searchInput,
  appliedSearch,
  loading,
  showSearch = true,
  searchLabel,
  itemLabel,
  emptyLabel,
  showLoadingLabel = true,
  showEmptyLabel = true,
  onSearchInput,
  onSearch,
  onClearSearch,
  onPageChange,
}: PaginationToolbarProps) {
  const { t } = useLanguage()
  const resolvedSearchLabel = searchLabel ?? t('pagination.searchSources')
  const resolvedItemLabel = itemLabel ?? t('common.items')
  const resolvedEmptyLabel = emptyLabel ?? t('common.noResults')
  const safeTotalPages = Math.max(1, totalPages)
  const searchId = useId()

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSearch()
  }

  return (
    <div className="grid gap-3 rounded-md border border-border bg-card p-4">
      {showSearch ? (
        <form className="flex flex-col gap-2 sm:flex-row sm:items-end" onSubmit={handleSubmit}>
          <div className="min-w-0 flex-1">
            <label className="text-sm font-medium" htmlFor={searchId}>
              {resolvedSearchLabel}
            </label>
            <Input
              id={searchId}
              aria-label={resolvedSearchLabel}
              className="mt-2"
              value={searchInput}
              onChange={(event) => onSearchInput(event.target.value)}
              placeholder={t('pagination.searchPlaceholder')}
            />
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={loading}>{t('common.search')}</Button>
            <Button
              type="button"
              variant="outline"
              disabled={loading || (!searchInput && !appliedSearch)}
              onClick={onClearSearch}
            >
              {t('common.clear')}
            </Button>
          </div>
        </form>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {loading ? (
          showLoadingLabel ? (
            <p className="text-sm text-muted-foreground" aria-live="polite">正在加载…</p>
          ) : null
        ) : total === 0 ? (
          showEmptyLabel ? (
            <p className="text-sm text-muted-foreground">{resolvedEmptyLabel}</p>
          ) : null
        ) : (
          <p className="text-sm text-muted-foreground">{t('pagination.summary', { page, totalPages: safeTotalPages, total, itemLabel: resolvedItemLabel })}</p>
        )}
        <div className="flex gap-2">
          <Button type="button" variant="outline" disabled={loading || page <= 1} onClick={() => onPageChange(page - 1)}>
            {t('common.previous')}
          </Button>
          <Button type="button" variant="outline" disabled={loading || page >= safeTotalPages} onClick={() => onPageChange(page + 1)}>
            {t('common.next')}
          </Button>
        </div>
      </div>
    </div>
  )
}
