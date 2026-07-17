import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { AppShell } from './AppShell'
import { AuthProvider } from './providers/AuthProvider'
import { ThemeProvider } from './providers/ThemeProvider'
import { AppRoutes } from './router'

test('unknown routes redirect to login when unauthenticated', async () => {
  render(
    <MemoryRouter
      initialEntries={['/missing']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ThemeProvider>
        <AuthProvider bootstrapSession={null}>
          <AppShell>
            <AppRoutes />
          </AppShell>
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>
  )

  expect(await screen.findByRole('heading', { name: /sign in/i })).toBeInTheDocument()
})

test('AI 工作台要求 ai.run 权限', async () => {
  render(
    <MemoryRouter
      initialEntries={['/ai/workspace']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider
        bootstrapSession={{
          accessToken: 'token',
          refreshToken: 'refresh',
          user: { id: '1', username: 'reader', permissions: [] },
        }}
      >
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>
  )

  expect(await screen.findByText('Access denied')).toBeInTheDocument()
})

test.each(['/dashboard', '/search', '/test', '/health', '/export'])('legacy path %s redirects to login', async (path) => {
  render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider bootstrapSession={null}>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByRole('heading', { name: /sign in/i })).toBeInTheDocument()
})
