import { StatusMessage } from '@/components/data/StatusMessage'

export interface SettingsEffectiveStatusProps {
  updatedAt: string | null | undefined
}

export function SettingsEffectiveStatus({ updatedAt }: SettingsEffectiveStatusProps) {
  const message = updatedAt
    ? `Effective ${new Date(updatedAt).toLocaleString()}`
    : 'Effective after the first save'

  return <StatusMessage tone="success" message={message} className="text-muted-foreground" />
}
