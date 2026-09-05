import { useId, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export interface FilterBarProps {
  label: string
  placeholder: string
  value: string
  loading: boolean
  clearDisabled: boolean
  submitLabel: string
  clearLabel: string
  onChange: (value: string) => void
  onSubmit: () => void
  onClear: () => void
}

export function FilterBar({
  label,
  placeholder,
  value,
  loading,
  clearDisabled,
  submitLabel,
  clearLabel,
  onChange,
  onSubmit,
  onClear,
}: FilterBarProps) {
  const inputId = useId()

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit()
  }

  return (
    <form className="flex flex-col gap-2 sm:flex-row sm:items-end" onSubmit={handleSubmit}>
      <div className="min-w-0 flex-1">
        <label className="text-sm font-medium" htmlFor={inputId}>{label}</label>
        <Input
          id={inputId}
          aria-label={label}
          className="mt-2"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
        />
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={loading}>{submitLabel}</Button>
        <Button type="button" variant="outline" disabled={clearDisabled} onClick={onClear}>{clearLabel}</Button>
      </div>
    </form>
  )
}
