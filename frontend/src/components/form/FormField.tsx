import { cloneElement, isValidElement, type ReactElement, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

export interface FormFieldProps {
  label: ReactNode
  htmlFor: string
  children: ReactElement<{ 'aria-describedby'?: string; 'aria-invalid'?: boolean }>
  help?: ReactNode
  error?: ReactNode
  className?: string
}

function bindDescription(
  children: ReactElement<{ 'aria-describedby'?: string; 'aria-invalid'?: boolean }>,
  describedBy: string,
  invalid: boolean,
) {
  if (!isValidElement(children)) return children
  const existing = children.props['aria-describedby']
  const ids = [existing, describedBy].filter(Boolean).join(' ')
  return cloneElement(children, {
    'aria-describedby': ids || undefined,
    'aria-invalid': invalid || undefined,
  })
}

export function FormField({ label, htmlFor, children, help, error, className }: FormFieldProps) {
  const helpId = `${htmlFor}-help`
  const errorId = `${htmlFor}-error`
  const describedBy = [help ? helpId : '', error ? errorId : ''].filter(Boolean).join(' ')

  return (
    <div className={cn('space-y-2', className)}>
      <label htmlFor={htmlFor} className="text-sm font-medium text-foreground">{label}</label>
      {bindDescription(children, describedBy, Boolean(error))}
      {help ? <p id={helpId} className="text-xs text-muted-foreground">{help}</p> : null}
      {error ? <p id={errorId} role="alert" className="text-xs text-destructive">{error}</p> : null}
    </div>
  )
}
