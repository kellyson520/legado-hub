import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useLanguage } from '@/app/providers/LanguageProvider'

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
    return <Card className="p-5 text-sm text-muted-foreground">{loadingLabel}</Card>
  }

  if (error) {
    return (
      <Card className="flex flex-wrap items-center gap-3 p-4 text-sm text-destructive" role="alert">
        <span>{errorLabel}</span>
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>{t('common.retry')}</Button>
      </Card>
    )
  }

  if (empty) {
    return <Card className="p-5 text-sm text-muted-foreground">{emptyLabel}</Card>
  }

  return null
}
