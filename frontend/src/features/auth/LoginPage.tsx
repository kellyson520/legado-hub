import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '@/app/providers/AuthProvider'

export function LoginPage() {
  const { login } = useAuth()
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
      setError(reason instanceof Error ? reason.message : 'Sign in failed')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
      <form onSubmit={submit} className="w-full max-w-sm rounded-md border border-border bg-card p-8 shadow-xl">
        <p className="text-xs font-semibold text-primary">LEGADO HUB</p>
        <h1 className="mt-3 text-3xl font-semibold text-foreground">Sign in</h1>
        <div className="mt-8 space-y-4">
          <label className="block text-sm text-muted-foreground">
            Username
            <input aria-label="Username" value={username} onChange={(event) => setUsername(event.target.value)} className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3 text-foreground outline-none focus:ring-2 focus:ring-ring" autoComplete="username" />
          </label>
          <label className="block text-sm text-muted-foreground">
            Password
            <input aria-label="Password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3 text-foreground outline-none focus:ring-2 focus:ring-ring" autoComplete="current-password" />
          </label>
          {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
          <button type="submit" disabled={pending} className="h-10 w-full rounded-md bg-primary text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90 disabled:opacity-50">
            {pending ? 'Signing in' : 'Sign in'}
          </button>
        </div>
      </form>
    </div>
  )
}
