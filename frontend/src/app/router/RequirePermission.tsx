import { Outlet } from 'react-router-dom'
import { useAuth } from '@/app/providers/AuthProvider'
import { useLanguage } from '@/app/providers/LanguageProvider'

export function RequirePermission({ permission }: { permission: string }) {
  const { hasPermission } = useAuth()
  const { t } = useLanguage()
  return hasPermission(permission) ? <Outlet /> : <p className="p-6 text-sm text-rose-300">{t('permission.denied')}</p>
}
