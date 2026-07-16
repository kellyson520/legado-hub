import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { vi } from 'vitest'

const login = vi.fn()
vi.mock('@/app/providers/AuthProvider', () => ({ useAuth: () => ({ login }) }))

import { LoginPage } from './LoginPage'

test('submits credentials and redirects after login', async () => {
  login.mockResolvedValue(undefined)
  render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/sources" element={<p>Sources page</p>} />
      </Routes>
    </MemoryRouter>
  )
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'admin123456' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(login).toHaveBeenCalledWith('admin', 'admin123456')
  expect(await screen.findByText('Sources page')).toBeInTheDocument()
})

test('shows a failed login message', async () => {
  login.mockRejectedValueOnce(new Error('Invalid username or password'))
  render(<MemoryRouter><LoginPage /></MemoryRouter>)
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByText('Invalid username or password')).toBeInTheDocument()
})

test('shows a clear credential hint for an HTTP 401 login failure', async () => {
  login.mockRejectedValueOnce(Object.assign(new Error('Request failed with status code 401'), {
    response: { status: 401 },
  }))
  render(<MemoryRouter><LoginPage /></MemoryRouter>)
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByText('用户名或密码错误，请检查后重试。')).toBeInTheDocument()
})
