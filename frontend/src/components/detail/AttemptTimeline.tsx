import type { ReactNode } from 'react'

import { StatusBadge } from '@/components/data/StatusBadge'
import { cn } from '@/lib/utils'

export interface AttemptTimelineItem {
  id: string | number
  label: ReactNode
  status: string
  detail?: ReactNode
}

export interface AttemptTimelineProps {
  items: AttemptTimelineItem[]
  className?: string
}

export function AttemptTimeline({ items, className }: AttemptTimelineProps) {
  return (
    <ol className={cn('space-y-3', className)} aria-label="Attempt history">
      {items.map((item) => (
        <li key={item.id} className="rounded-md border border-border bg-muted/20 p-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="font-medium text-foreground">{item.label}</span>
            <StatusBadge status={item.status} />
          </div>
          {item.detail ? <p className="mt-2 text-muted-foreground">{item.detail}</p> : null}
        </li>
      ))}
    </ol>
  )
}
