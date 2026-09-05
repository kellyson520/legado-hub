import { useLanguage } from '@/app/providers/LanguageProvider'
import { EmptyState, ErrorState, LoadingState } from '@/components/data/ListStates'

export interface ListStatusProps {
  loading: boolean
  error: Error | null
  empty: boolean
  onRetry: () => void
  loadingLabel: string
  errorLabel: string
  emptyLabel: string
}

export function ListStatus({
  loading,
  error,
  empty,
  onRetry,
  loadingLabel,
  errorLabel,
  emptyLabel,
}: ListStatusProps) {
  const { t } = useLanguage()
  if (loading) {
    return <LoadingState label={loadingLabel} />
  }

  if (error) {
    return <ErrorState label={errorLabel} onRetry={onRetry} retryLabel={t('common.retry')} />
  }

  if (empty) {
    return <EmptyState label={emptyLabel} />
  }

  return null
}
