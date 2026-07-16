import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export interface StatusMessageProps {
  tone: 'success' | 'error'
  message: ReactNode
  as?: 'p' | 'span' | 'div'
  className?: string
}

const toneClasses = {
  success: 'text-emerald-600 dark:text-emerald-400',
  error: 'text-destructive',
} as const

export function StatusMessage({ tone, message, as: Element = 'p', className }: StatusMessageProps) {
  if (message === null || message === undefined || message === '') return null

  return (
    <Element
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn('text-sm', toneClasses[tone], className)}
    >
      {message}
    </Element>
  )
}
