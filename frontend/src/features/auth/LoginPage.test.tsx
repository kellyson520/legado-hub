import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { vi } from 'vitest'

import { LanguageProvider } from '@/app/providers/LanguageProvider'

const login = vi.fn()
vi.mock('@/app/providers/AuthProvider', () => ({ useAuth: () => ({ login }) }))

import { LoginPage } from './LoginPage'

function renderLogin() {
  return render(<LanguageProvider><MemoryRouter><LoginPage /></MemoryRouter></LanguageProvider>)
}

test('submits credentials and redirects after login', async () => {
  login.mockResolvedValue(undefined)
  render(
    <LanguageProvider>
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/sources" element={<p>Sources page</p>} />
        </Routes>
      </MemoryRouter>
    </LanguageProvider>
  )
  fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'admin' } })
  fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'admin123456' } })
  fireEvent.click(screen.getByRole('button', { name: '登录' }))
  expect(login).toHaveBeenCalledWith('admin', 'admin123456')
  expect(await screen.findByText('Sources page')).toBeInTheDocument()
})

test('shows a failed login message', async () => {
  login.mockRejectedValueOnce(new Error('Invalid username or password'))
  renderLogin()
  fireEvent.click(screen.getByRole('button', { name: '登录' }))
  expect(await screen.findByText('用户名或密码错误，请检查后重试。')).toBeInTheDocument()
})

test('shows a clear credential hint for an HTTP 401 login failure', async () => {
  login.mockRejectedValueOnce(Object.assign(new Error('Request failed with status code 401'), {
    response: { status: 401 },
  }))
  renderLogin()
  fireEvent.click(screen.getByRole('button', { name: '登录' }))
  expect(await screen.findByText('用户名或密码错误，请检查后重试。')).toBeInTheDocument()
})

test('switches the login form to English', () => {
  renderLogin()

  fireEvent.click(screen.getByRole('button', { name: 'English' }))

  expect(screen.getByLabelText('Username')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '中文' })).toBeInTheDocument()
})
