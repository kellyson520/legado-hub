import type { ReactNode } from 'react'

import { EmptyState } from '@/components/data/ListStates'
import { SectionHeader } from '@/components/layout/SectionHeader'
import { cn } from '@/lib/utils'

export interface DetailItem {
  label: ReactNode
  value: ReactNode
}

export interface DetailPanelProps {
  title: ReactNode
  description?: ReactNode
  items?: DetailItem[]
  emptyLabel?: ReactNode
  children?: ReactNode
  className?: string
}

export function DetailPanel({ title, description, items, emptyLabel = 'No details', children, className }: DetailPanelProps) {
  const hasItems = Boolean(items?.length)
  const hasChildren = children !== undefined && children !== null

  return (
    <section className={cn('rounded-md border border-border bg-card p-4', className)}>
      <SectionHeader title={title} description={description} />
      {hasChildren ? (
        <div className="mt-4">{children}</div>
      ) : hasItems ? (
        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          {items?.map((item, index) => (
            <div key={`${String(item.label)}-${index}`} className="min-w-0 rounded-md border border-border bg-muted/20 p-3">
              <dt className="text-xs font-medium text-muted-foreground">{item.label}</dt>
              <dd className="mt-1 break-words text-sm text-foreground">{item.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <div className="mt-4"><EmptyState label={emptyLabel} /></div>
      )}
    </section>
  )
}
