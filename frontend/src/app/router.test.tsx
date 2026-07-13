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
