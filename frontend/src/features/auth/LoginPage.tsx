import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '@/app/providers/AuthProvider'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { LanguageToggle } from '@/components/layout/LanguageToggle'
import { StatusMessage } from '@/components/data/StatusMessage'

function loginErrorMessage(reason: unknown, t: (key: string) => string) {
  if (
    typeof reason === 'object'
    && reason !== null
    && 'response' in reason
    && typeof reason.response === 'object'
    && reason.response !== null
    && 'status' in reason.response
    && reason.response.status === 401
  ) {
    return t('auth.invalidCredentials')
  }
  if (reason instanceof Error && reason.message === 'Invalid username or password') {
    return t('auth.invalidCredentials')
  }
  return reason instanceof Error ? reason.message : t('auth.signInFailed')
}

export function LoginPage() {
  const { login } = useAuth()
  const { t } = useLanguage()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setPending(true)
    try {
      await login(username, password)
      const from = (location.state as { from?: string } | null)?.from || '/sources'
      navigate(from, { replace: true })
    } catch (reason) {
      setError(loginErrorMessage(reason, t))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
      <LanguageToggle className="absolute right-6 top-6" />
      <form onSubmit={submit} className="w-full max-w-sm rounded-md border border-border bg-card p-8 shadow-xl">
        <p className="text-xs font-semibold text-primary">{t('auth.brand')}</p>
        <h1 className="mt-3 text-3xl font-semibold text-foreground">{t('auth.signIn')}</h1>
        <div className="mt-8 space-y-4">
          <label className="block text-sm text-muted-foreground">
            {t('auth.username')}
            <input aria-label={t('auth.username')} value={username} onChange={(event) => setUsername(event.target.value)} className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3 text-foreground outline-none focus:ring-2 focus:ring-ring" autoComplete="username" />
          </label>
          <label className="block text-sm text-muted-foreground">
            {t('auth.password')}
            <input aria-label={t('auth.password')} type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3 text-foreground outline-none focus:ring-2 focus:ring-ring" autoComplete="current-password" />
          </label>
          <StatusMessage tone="error" message={error} />
          <button type="submit" disabled={pending} className="h-10 w-full rounded-md bg-primary text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90 disabled:opacity-50">
            {t('auth.signIn')}
          </button>
        </div>
      </form>
    </div>
  )
}
