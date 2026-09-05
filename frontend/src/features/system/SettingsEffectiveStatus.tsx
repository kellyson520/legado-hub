import { StatusMessage } from '@/components/data/StatusMessage'
import { useLanguage } from '@/app/providers/LanguageProvider'

export interface SettingsEffectiveStatusProps {
  updatedAt: string | null | undefined
}

export function SettingsEffectiveStatus({ updatedAt }: SettingsEffectiveStatusProps) {
  const { t } = useLanguage()
  const message = updatedAt
    ? `${t('settings.effective')} ${new Date(updatedAt).toLocaleString()}`
    : t('settings.effectiveAfterSave')

  return <StatusMessage tone="success" message={message} className="text-muted-foreground" />
}
