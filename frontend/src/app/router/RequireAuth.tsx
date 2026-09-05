import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/app/providers/AuthProvider'
import { useLanguage } from '@/app/providers/LanguageProvider'

export function RequireAuth() {
  const { session, initializing, restoreFailed, retrySessionRestore } = useAuth()
  const { t } = useLanguage()
  const location = useLocation()
  const navigate = useNavigate()
  if (initializing) return <p className="p-6 text-sm text-muted-foreground">{t('auth.restoring')}</p>
  if (restoreFailed) {
    return (
      <div className="space-y-3 p-6 text-sm">
        <p className="text-muted-foreground">{t('auth.restoreFailed')}</p>
        <div className="flex gap-2">
          <button className="rounded-md border border-input px-3 py-2" onClick={() => void retrySessionRestore()}>{t('common.retry')}</button>
          <button className="rounded-md bg-primary px-3 py-2 text-primary-foreground" onClick={() => navigate('/login', { replace: true })}>{t('auth.relogin')}</button>
        </div>
      </div>
    )
  }
  return session ? <Outlet /> : <Navigate to="/login" replace state={{ from: location.pathname }} />
}
