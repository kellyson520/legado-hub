import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export interface FormActionsProps {
  children: ReactNode
  className?: string
}

export function FormActions({ children, className }: FormActionsProps) {
  return <div className={cn('flex flex-wrap items-center justify-end gap-2', className)}>{children}</div>
}
