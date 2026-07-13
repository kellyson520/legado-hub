import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test } from 'vitest'

import type { AuthSession } from '@/api/types'
import { AuthProvider } from '@/app/providers/AuthProvider'
import { ThemeProvider } from '@/app/providers/ThemeProvider'
import { AppConsoleShell } from './AppConsoleShell'

const sourceReader: AuthSession = {
  accessToken: 'access-token',
  refreshToken: 'refresh-token',
  user: { id: '1', username: 'reader', permissions: ['book_sources.read'] },
}

function renderShell() {
  render(
    <MemoryRouter initialEntries={['/sources']}>
      <ThemeProvider>
        <AuthProvider bootstrapSession={sourceReader}>
          <AppConsoleShell><div>Content</div></AppConsoleShell>
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>
  )
}

afterEach(() => {
  window.localStorage.clear()
  document.documentElement.className = ''
})

test('shows only navigation entries allowed by the current session', () => {
  renderShell()

  expect(screen.getByRole('link', { name: '书源' })).toBeVisible()
  expect(screen.queryByRole('link', { name: '用户管理' })).not.toBeInTheDocument()
})

test('opens and closes the mobile navigation drawer', () => {
  renderShell()

  fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
  expect(screen.getByRole('dialog', { name: '导航菜单' })).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: '关闭导航' }))
  expect(screen.queryByRole('dialog', { name: '导航菜单' })).not.toBeInTheDocument()
})
