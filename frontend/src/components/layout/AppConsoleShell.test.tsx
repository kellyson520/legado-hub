import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test } from 'vitest'

import type { AuthSession } from '@/api/types'
import { AuthProvider } from '@/app/providers/AuthProvider'
import { LanguageProvider } from '@/app/providers/LanguageProvider'
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
      <LanguageProvider>
        <ThemeProvider>
          <AuthProvider bootstrapSession={sourceReader}>
            <AppConsoleShell><div>Content</div></AppConsoleShell>
          </AuthProvider>
        </ThemeProvider>
      </LanguageProvider>
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
  expect(screen.getByRole('dialog', { name: '主导航' })).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: '关闭导航' }))
  expect(screen.queryByRole('dialog', { name: '导航菜单' })).not.toBeInTheDocument()
})

test('switches shell navigation to English without a page reload', () => {
  renderShell()

  fireEvent.click(screen.getByRole('button', { name: 'English' }))

  expect(screen.getByRole('link', { name: 'Book Sources' })).toBeVisible()
  expect(screen.getByText('Console / Book Sources')).toBeVisible()
  expect(screen.getByRole('button', { name: '中文' })).toBeVisible()
})
