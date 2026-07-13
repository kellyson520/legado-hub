import { act, render, screen } from '@testing-library/react'
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

import { getConfiguredAccessToken } from '@/api/client'
import { RequireAuth } from '@/app/router/RequireAuth'
import { AuthProvider } from './AuthProvider'

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
  window.sessionStorage.clear()
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
  expect(window.sessionStorage.getItem('legado.refresh-token')).toBe('new-refresh')
})
