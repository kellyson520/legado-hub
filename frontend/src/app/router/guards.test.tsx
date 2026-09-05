import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen } from '@testing-library/react'

import { AuthProvider } from '@/app/providers/AuthProvider'
import { RequireAuth } from './RequireAuth'
import { RequirePermission } from './RequirePermission'

test('redirects an anonymous user to login', async () => {
  render(
    <AuthProvider bootstrapSession={null}>
      <MemoryRouter initialEntries={['/sources']}>
        <Routes>
          <Route path="/login" element={<p>Login page</p>} />
          <Route element={<RequireAuth />}><Route path="/sources" element={<p>Sources page</p>} /></Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )
  expect(await screen.findByText('Login page')).toBeInTheDocument()
})

test('renders access denied without the required backend permission', async () => {
  render(
    <AuthProvider bootstrapSession={{ accessToken: 'a', refreshToken: 'r', user: { id: '1', username: 'operator', permissions: [] } }}>
      <MemoryRouter initialEntries={['/sources']}>
        <Routes>
          <Route element={<RequireAuth />}>
            <Route element={<RequirePermission permission="book_sources.read" />}><Route path="/sources" element={<p>Sources page</p>} /></Route>
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )
  expect(await screen.findByText('无权访问')).toBeInTheDocument()
})
