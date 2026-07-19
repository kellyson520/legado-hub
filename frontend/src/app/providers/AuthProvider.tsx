import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import type { AuthSession } from '@/api/types'
import { configureAuthClient, type AuthFailureOptions } from '@/api/client'
import { createAuthSession, getCurrentUser, login as loginRequest, logout as logoutRequest, refreshSession } from '@/api/modules/auth'
import { hasPermission as checkPermission } from '@/lib/permissions'

const REFRESH_TOKEN_STORAGE_KEY = 'legado.refresh-token'
const SESSION_RESTORE_TIMEOUT_MS = 10_000

function readStoredRefreshToken() {
  if (typeof window === 'undefined') return null
  try {
    return window.sessionStorage.getItem(REFRESH_TOKEN_STORAGE_KEY)
      ?? window.localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStoredRefreshToken(token: string | null) {
  if (typeof window === 'undefined') return
  try {
    if (token) {
      window.sessionStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, token)
      window.localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, token)
    } else {
      window.sessionStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY)
      window.localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY)
    }
  } catch {
    // Private browsing modes may deny storage access; in-memory auth still works.
  }
}

function isUnauthorized(error: unknown) {
  if (!error || typeof error !== 'object') return false
  const response = (error as { response?: { status?: unknown } }).response
  return response?.status === 401
}

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
  const refreshAttemptRef = useRef(0)

  function invalidateRefreshAttempt() {
    refreshAttemptRef.current += 1
    refreshPromiseRef.current = null
  }

  function setSession(next: AuthSession | null, persist = true) {
    if (!next) invalidateRefreshAttempt()
    sessionRef.current = next
    setSessionState(next)
    if (!persist || typeof window === 'undefined') return
    writeStoredRefreshToken(next?.refreshToken ?? null)
  }

  async function refresh(): Promise<AuthSession | null> {
    if (refreshPromiseRef.current) return refreshPromiseRef.current
    const refreshAttempt = refreshAttemptRef.current + 1
    refreshAttemptRef.current = refreshAttempt
    const currentPromise = (async () => {
      const refreshToken = sessionRef.current?.refreshToken ?? readStoredRefreshToken()
      if (!refreshToken) return null
      try {
        const tokens = await refreshSession(refreshToken)
        if (refreshAttemptRef.current !== refreshAttempt) return null
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
        const identity = await getCurrentUser({ skipAuthRefresh: true })
        if (refreshAttemptRef.current !== refreshAttempt) return null
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
      } catch (error) {
        // Keep the token for a retry when the failure is transient. An explicit
        // 401 means the server rejected this refresh session and requires login.
        if (refreshAttemptRef.current === refreshAttempt) setSession(null, isUnauthorized(error))
        return null
      } finally {
        if (refreshAttemptRef.current === refreshAttempt) refreshPromiseRef.current = null
      }
    })()
    refreshPromiseRef.current = currentPromise
    return currentPromise
  }

  async function login(username: string, password: string) {
    invalidateRefreshAttempt()
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
    invalidateRefreshAttempt()
    try { if (sessionRef.current) await logoutRequest() } finally { setSession(null) }
  }

  async function restoreSession() {
    const refreshToken = sessionRef.current?.refreshToken ?? readStoredRefreshToken()
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
        new Promise<null>((_, reject) => window.setTimeout(() => reject(new Error('Session restore timed out')), SESSION_RESTORE_TIMEOUT_MS)),
      ])
      setRestoreFailed(!restored)
    } catch {
      setSession(null, false)
      setRestoreFailed(true)
    } finally {
      setInitializing(false)
    }
  }

  useEffect(() => {
    configureAuthClient({
      getAccessToken: () => sessionRef.current?.accessToken ?? null,
      refresh,
      onAuthFailure: (options: AuthFailureOptions = {}) => setSession(null, options.clearStoredToken === true),
    })
    if (bootstrapSession === undefined) void restoreSession()
    else setInitializing(false)
    return () => {
      invalidateRefreshAttempt()
      configureAuthClient(null)
    }
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
