import { act, fireEvent, render, screen } from '@testing-library/react'
import { AxiosError } from 'axios'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({
  refreshSession: vi.fn(() => new Promise(() => undefined)),
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  createAuthSession: vi.fn((tokens, identity, username, previousRefreshToken) => ({
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token ?? previousRefreshToken,
    user: { id: String(identity.user_id), username, permissions: identity.permissions },
  })),
}))

vi.mock('@/api/modules/auth', () => ({
  refreshSession: authMocks.refreshSession,
  getCurrentUser: authMocks.getCurrentUser,
  login: authMocks.login,
  logout: authMocks.logout,
  createAuthSession: authMocks.createAuthSession,
}))

import { apiClient, getConfiguredAccessToken } from '@/api/client'
import { RequireAuth } from '@/app/router/RequireAuth'
import { AuthProvider, useAuth } from './AuthProvider'

function SessionActions() {
  const { clearSession, login, logout, session } = useAuth()
  return (
    <>
      <button onClick={() => clearSession()}>清除会话</button>
      <button onClick={() => void login('new-user', 'password')}>登录新会话</button>
      <button onClick={() => void logout()}>退出会话</button>
      <span data-testid="session-user">{session?.user.username ?? 'none'}</span>
    </>
  )
}

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
  window.sessionStorage.clear()
  window.localStorage.clear()
})

test('ends a stalled session restore with a retry action', async () => {
  vi.useFakeTimers()
  window.sessionStorage.setItem('legado.refresh-token', 'refresh-token')
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/sources']}>
        <Routes>
          <Route path="/login" element={<p>Login</p>} />
          <Route element={<RequireAuth />}>
            <Route path="/sources" element={<p>Sources</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )

  expect(screen.getByText('正在恢复会话')).toBeInTheDocument()
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3_000)
  })
  expect(screen.getByText('正在恢复会话')).toBeInTheDocument()
  await act(async () => {
    await vi.advanceTimersByTimeAsync(7_000)
  })
  expect(screen.getByRole('button', { name: '重新登录' })).toBeInTheDocument()
})

test('restores a refreshed session after page reload using the new access token for identity lookup', async () => {
  window.sessionStorage.setItem('legado.refresh-token', 'stored-refresh')
  authMocks.refreshSession.mockResolvedValueOnce({
    access_token: 'new-access',
    refresh_token: 'new-refresh',
    permissions: ['book_sources.read'],
  })
  authMocks.getCurrentUser.mockImplementationOnce(async () => {
    expect(getConfiguredAccessToken()).toBe('new-access')
    return { user_id: 7, permissions: ['book_sources.read'], session_id: 'session-7' }
  })

  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/sources']}>
        <Routes>
          <Route path="/login" element={<p>Login</p>} />
          <Route element={<RequireAuth />}>
            <Route path="/sources" element={<p>Sources restored</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )

  expect(await screen.findByText('Sources restored')).toBeInTheDocument()
  expect(authMocks.getCurrentUser).toHaveBeenCalledWith({ skipAuthRefresh: true })
  expect(window.sessionStorage.getItem('legado.refresh-token')).toBe('new-refresh')
})

test('restores a session from persistent storage when tab storage is empty', async () => {
  window.localStorage.setItem('legado.refresh-token', 'persistent-refresh')
  authMocks.refreshSession.mockResolvedValueOnce({
    access_token: 'persistent-access',
    refresh_token: 'persistent-refresh',
    permissions: ['book_sources.read'],
  })
  authMocks.getCurrentUser.mockResolvedValueOnce({ user_id: 7, permissions: ['book_sources.read'], session_id: 'session-7' })

  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/sources']}>
        <Routes>
          <Route path="/login" element={<p>Login</p>} />
          <Route element={<RequireAuth />}>
            <Route path="/sources" element={<p>Sources persisted</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )

  expect(await screen.findByText('Sources persisted')).toBeInTheDocument()
  expect(window.sessionStorage.getItem('legado.refresh-token')).toBe('persistent-refresh')
})

test('keeps the refresh token available when session restore fails transiently', async () => {
  window.sessionStorage.setItem('legado.refresh-token', 'retryable-refresh')
  authMocks.refreshSession.mockRejectedValueOnce(new Error('network unavailable'))

  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/sources']}>
        <Routes>
          <Route path="/login" element={<p>Login</p>} />
          <Route element={<RequireAuth />}>
            <Route path="/sources" element={<p>Sources retryable</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )

  expect(await screen.findByRole('button', { name: '重试' })).toBeInTheDocument()
  expect(window.sessionStorage.getItem('legado.refresh-token')).toBe('retryable-refresh')
})

test('clears invalid refresh credentials after the server rejects the session', async () => {
  window.sessionStorage.setItem('legado.refresh-token', 'invalid-refresh')
  window.localStorage.setItem('legado.refresh-token', 'invalid-refresh')
  authMocks.refreshSession.mockRejectedValueOnce({ response: { status: 401 } })

  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/sources']}>
        <Routes>
          <Route path="/login" element={<p>Login</p>} />
          <Route element={<RequireAuth />}>
            <Route path="/sources" element={<p>Sources invalid</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )

  expect(await screen.findByRole('button', { name: '重新登录' })).toBeInTheDocument()
  expect(window.sessionStorage.getItem('legado.refresh-token')).toBeNull()
  expect(window.localStorage.getItem('legado.refresh-token')).toBeNull()
})

test('starts a fresh restore request after a previous restore timed out', async () => {
  vi.useFakeTimers()
  window.sessionStorage.setItem('legado.refresh-token', 'timeout-refresh')
  authMocks.refreshSession
    .mockImplementationOnce(() => new Promise(() => undefined))
    .mockResolvedValueOnce({
      access_token: 'recovered-access',
      refresh_token: 'timeout-refresh',
      permissions: ['book_sources.read'],
    })
  authMocks.getCurrentUser.mockResolvedValueOnce({ user_id: 7, permissions: ['book_sources.read'], session_id: 'session-7' })

  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/sources']}>
        <Routes>
          <Route path="/login" element={<p>Login</p>} />
          <Route element={<RequireAuth />}>
            <Route path="/sources" element={<p>Sources after timeout</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )

  await act(async () => {
    await vi.advanceTimersByTimeAsync(10_000)
  })
  fireEvent.click(screen.getByRole('button', { name: '重试' }))
  expect(authMocks.refreshSession).toHaveBeenCalledTimes(2)
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
  expect(screen.getByText('Sources after timeout')).toBeInTheDocument()
})

test('does not let a stale restore revive a session after it is cleared', async () => {
  let resolveRefresh: (tokens: { access_token: string; refresh_token: string }) => void = () => undefined
  authMocks.refreshSession.mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve }))
  window.sessionStorage.setItem('legado.refresh-token', 'stale-refresh')

  render(
    <AuthProvider>
      <SessionActions />
    </AuthProvider>
  )

  fireEvent.click(screen.getByRole('button', { name: '清除会话' }))
  await act(async () => {
    resolveRefresh({ access_token: 'old-access', refresh_token: 'old-refresh' })
    await Promise.resolve()
    await Promise.resolve()
  })

  expect(screen.getByTestId('session-user')).toHaveTextContent('none')
  expect(authMocks.getCurrentUser).not.toHaveBeenCalled()
  expect(window.sessionStorage.getItem('legado.refresh-token')).toBeNull()
})

test('does not let a stale restore revive a session after a new login', async () => {
  let resolveRefresh: (tokens: { access_token: string; refresh_token: string }) => void = () => undefined
  authMocks.refreshSession.mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve }))
  authMocks.login.mockResolvedValueOnce({ access_token: 'new-access', refresh_token: 'new-refresh', permissions: [] })
  authMocks.getCurrentUser.mockResolvedValueOnce({ user_id: 9, permissions: [], session_id: 'new-session' })
  window.sessionStorage.setItem('legado.refresh-token', 'stale-refresh')

  render(
    <AuthProvider>
      <SessionActions />
    </AuthProvider>
  )

  fireEvent.click(screen.getByRole('button', { name: '登录新会话' }))
  expect(await screen.findByText('new-user')).toBeInTheDocument()
  await act(async () => {
    resolveRefresh({ access_token: 'old-access', refresh_token: 'old-refresh' })
    await Promise.resolve()
    await Promise.resolve()
  })

  expect(screen.getByTestId('session-user')).toHaveTextContent('new-user')
  expect(window.sessionStorage.getItem('legado.refresh-token')).toBe('new-refresh')
})

test('does not let a stale restore revive a session after logout', async () => {
  let resolveRefresh: (tokens: { access_token: string; refresh_token: string }) => void = () => undefined
  authMocks.refreshSession.mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve }))
  window.sessionStorage.setItem('legado.refresh-token', 'stale-refresh')

  render(
    <AuthProvider>
      <SessionActions />
    </AuthProvider>
  )

  fireEvent.click(screen.getByRole('button', { name: '退出会话' }))
  await act(async () => {
    resolveRefresh({ access_token: 'old-access', refresh_token: 'old-refresh' })
    await Promise.resolve()
    await Promise.resolve()
  })

  expect(screen.getByTestId('session-user')).toHaveTextContent('none')
  expect(authMocks.getCurrentUser).not.toHaveBeenCalled()
  expect(window.sessionStorage.getItem('legado.refresh-token')).toBeNull()
})

test('clears both persistent refresh tokens when an API retry remains unauthorized', async () => {
  window.sessionStorage.setItem('legado.refresh-token', 'old-refresh')
  window.localStorage.setItem('legado.refresh-token', 'old-refresh')
  authMocks.refreshSession.mockResolvedValueOnce({
    access_token: 'fresh-access',
    refresh_token: 'fresh-refresh',
    permissions: [],
  })
  authMocks.getCurrentUser.mockResolvedValueOnce({ user_id: 7, permissions: [], session_id: 'session-7' })

  render(
    <AuthProvider
      bootstrapSession={{
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
        user: { id: '7', username: 'operator', permissions: [] },
      }}
    >
      <SessionActions />
    </AuthProvider>
  )

  const previousAdapter = apiClient.raw.defaults.adapter
  let attempts = 0
  apiClient.raw.defaults.adapter = async (config) => {
    attempts += 1
    throw new AxiosError(
      `unauthorized attempt ${attempts}`,
      'ERR_BAD_REQUEST',
      config,
      undefined,
      {
        data: { success: false, code: 'AUTHENTICATION_ERROR', message: 'unauthorized', data: null, meta: {}, trace_id: null },
        status: 401,
        statusText: 'Unauthorized',
        headers: {},
        config,
      }
    )
  }

  try {
    await act(async () => {
      await expect(apiClient.get('/protected')).rejects.toBeInstanceOf(AxiosError)
    })
  } finally {
    apiClient.raw.defaults.adapter = previousAdapter
  }

  expect(attempts).toBe(2)
  expect(window.sessionStorage.getItem('legado.refresh-token')).toBeNull()
  expect(window.localStorage.getItem('legado.refresh-token')).toBeNull()
})
