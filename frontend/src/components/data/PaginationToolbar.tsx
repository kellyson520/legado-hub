import { useLanguage } from '@/app/providers/LanguageProvider'
import { FilterBar } from '@/components/data/FilterBar'
import { Button } from '@/components/ui/button'

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
  return (
    <div className="grid gap-3 rounded-md border border-border bg-card p-4">
      {showSearch ? (
        <FilterBar
          label={resolvedSearchLabel}
          placeholder={t('pagination.searchPlaceholder')}
          value={searchInput}
          loading={loading}
          clearDisabled={loading || (!searchInput && !appliedSearch)}
          submitLabel={t('common.search')}
          clearLabel={t('common.clear')}
          onChange={onSearchInput}
          onSubmit={onSearch}
          onClear={onClearSearch}
        />
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
