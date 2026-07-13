import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import type { AuthSession } from '@/api/types'
import { configureAuthClient } from '@/api/client'
import { createAuthSession, getCurrentUser, login as loginRequest, logout as logoutRequest, refreshSession } from '@/api/modules/auth'
import { hasPermission as checkPermission } from '@/lib/permissions'

interface AuthContextValue {
  session: AuthSession | null
  setSession: (session: AuthSession | null) => void
  clearSession: () => void
  hasPermission: (permission: string) => boolean
  isAdmin: boolean
  initializing: boolean
  restoreFailed: boolean
  retrySessionRestore: () => Promise<void>
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({
  children,
  bootstrapSession,
}: {
  children: ReactNode
  bootstrapSession?: AuthSession | null
}) {
  const [session, setSessionState] = useState<AuthSession | null>(bootstrapSession ?? null)
  const [initializing, setInitializing] = useState(bootstrapSession === undefined)
  const [restoreFailed, setRestoreFailed] = useState(false)
  const sessionRef = useRef<AuthSession | null>(bootstrapSession ?? null)
  const refreshPromiseRef = useRef<Promise<AuthSession | null> | null>(null)

  function setSession(next: AuthSession | null, persist = true) {
    sessionRef.current = next
    setSessionState(next)
    if (!persist || typeof window === 'undefined') return
    if (next) window.sessionStorage.setItem('legado.refresh-token', next.refreshToken)
    else window.sessionStorage.removeItem('legado.refresh-token')
  }

  async function refresh(): Promise<AuthSession | null> {
    if (refreshPromiseRef.current) return refreshPromiseRef.current
    refreshPromiseRef.current = (async () => {
      const refreshToken = sessionRef.current?.refreshToken ?? window.sessionStorage.getItem('legado.refresh-token')
      if (!refreshToken) return null
      try {
        const tokens = await refreshSession(refreshToken)
        const provisionalRefreshToken = tokens.refresh_token ?? refreshToken
        sessionRef.current = {
          accessToken: tokens.access_token,
          refreshToken: provisionalRefreshToken,
          user: sessionRef.current?.user ?? {
            id: '0',
            username: 'restoring',
            roles: tokens.roles ?? [],
            permissions: tokens.permissions ?? [],
          },
        }
        const identity = await getCurrentUser()
        const next = createAuthSession(
          tokens,
          identity,
          sessionRef.current?.user.username && sessionRef.current.user.username !== 'restoring'
            ? sessionRef.current.user.username
            : `user-${identity.user_id}`,
          provisionalRefreshToken
        )
        setSession(next)
        return next
      } catch {
        setSession(null)
        return null
      } finally {
        refreshPromiseRef.current = null
      }
    })()
    return refreshPromiseRef.current
  }

  async function login(username: string, password: string) {
    const tokens = await loginRequest({ username, password })
    const provisional = createAuthSession(tokens, { user_id: 0, permissions: tokens.permissions ?? [], roles: tokens.roles ?? [], display_name: tokens.display_name, session_id: null }, username)
    setSession(provisional)
    try {
      const identity = await getCurrentUser()
      setSession(createAuthSession(tokens, identity, username, provisional.refreshToken))
    } catch (error) {
      setSession(null)
      throw error
    }
  }

  async function logout() {
    try { if (sessionRef.current) await logoutRequest() } finally { setSession(null) }
  }

  async function restoreSession() {
    const refreshToken = sessionRef.current?.refreshToken ?? window.sessionStorage.getItem('legado.refresh-token')
    if (!refreshToken) {
      setRestoreFailed(false)
      setInitializing(false)
      return
    }
    setInitializing(true)
    setRestoreFailed(false)
    try {
      const restored = await Promise.race([
        refresh(),
        new Promise<null>((_, reject) => window.setTimeout(() => reject(new Error('Session restore timed out')), 3_000)),
      ])
      setRestoreFailed(!restored)
    } catch {
      setSession(null)
      setRestoreFailed(true)
    } finally {
      setInitializing(false)
    }
  }

  useEffect(() => {
    configureAuthClient({ getAccessToken: () => sessionRef.current?.accessToken ?? null, refresh, onAuthFailure: () => setSession(null) })
    if (bootstrapSession === undefined) void restoreSession()
    else setInitializing(false)
    return () => configureAuthClient(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      setSession,
      clearSession: () => setSession(null),
      hasPermission: (permission: string) => checkPermission(session?.user.permissions, permission),
      isAdmin: session?.user.roles?.includes('admin') ?? false,
      initializing,
      restoreFailed,
      retrySessionRestore: restoreSession,
      login,
      logout,
    }),
    [initializing, restoreFailed, session]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
