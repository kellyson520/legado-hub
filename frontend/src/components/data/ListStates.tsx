import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

export function LoadingState({ label }: { label: ReactNode }) {
  return <Card className="p-5 text-sm text-muted-foreground" aria-live="polite">{label}</Card>
}

export function ErrorState({ label, onRetry, retryLabel }: { label: ReactNode; onRetry: () => void; retryLabel: ReactNode }) {
  return (
    <Card className="flex flex-wrap items-center gap-3 p-4 text-sm text-destructive" role="alert">
      <span>{label}</span>
      <Button type="button" variant="outline" size="sm" onClick={onRetry}>{retryLabel}</Button>
    </Card>
  )
}

export function EmptyState({ label }: { label: ReactNode }) {
  return <Card className="p-5 text-sm text-muted-foreground">{label}</Card>
}
