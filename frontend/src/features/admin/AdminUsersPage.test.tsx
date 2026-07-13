import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

const adminMocks = vi.hoisted(() => ({
  listUsers: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{
      id: '2',
      username: 'reader',
      display_name: '读者',
      role: 'user',
      roles: ['user'],
      status: 'enabled',
    }],
    meta: { total: 1 },
    trace_id: null,
  }),
  createUser: vi.fn().mockResolvedValue({ data: {} }),
  updateUser: vi.fn().mockResolvedValue({ data: {} }),
  setUserEnabled: vi.fn().mockResolvedValue({ data: {} }),
  resetUserPassword: vi.fn().mockResolvedValue({ data: {} }),
  revokeUserSessions: vi.fn().mockResolvedValue({ data: {} }),
}))

vi.mock('@/api/modules/admin', () => adminMocks)

import { AuthProvider } from '@/app/providers/AuthProvider'
import { AdminUsersPage } from './AdminUsersPage'

function renderAsUserManager() {
  return render(
    <AuthProvider
      bootstrapSession={{
        accessToken: 'token',
        refreshToken: 'refresh',
        user: {
          id: '1',
          username: 'admin',
          permissions: ['users.read', 'users.write'],
          roles: ['admin'],
        },
      }}
    >
      <AdminUsersPage />
    </AuthProvider>
  )
}

test('管理员可创建、编辑、改密和撤销用户会话', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  renderAsUserManager()

  fireEvent.click(await screen.findByRole('button', { name: '创建用户' }))
  fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'new-reader' } })
  fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: '新读者' } })
  fireEvent.change(screen.getByLabelText('初始密码'), { target: { value: 'ReaderPass123' } })
  fireEvent.click(screen.getByRole('button', { name: '确认创建' }))

  await waitFor(() => {
    expect(adminMocks.createUser).toHaveBeenCalledWith({
      username: 'new-reader',
      display_name: '新读者',
      role: 'user',
      password: 'ReaderPass123',
    })
  })

  fireEvent.click(screen.getByRole('button', { name: '编辑' }))
  fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: '资深读者' } })
  fireEvent.click(screen.getByRole('button', { name: '保存修改' }))

  await waitFor(() => {
    expect(adminMocks.updateUser).toHaveBeenCalledWith('2', {
      display_name: '资深读者',
      role: 'user',
    })
  })

  fireEvent.click(screen.getByRole('button', { name: '重置密码' }))
  fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'ChangedPass456' } })
  fireEvent.click(screen.getByRole('button', { name: '确认重置' }))

  await waitFor(() => {
    expect(adminMocks.resetUserPassword).toHaveBeenCalledWith('2', 'ChangedPass456')
  })

  fireEvent.click(screen.getByRole('button', { name: '撤销会话' }))
  await waitFor(() => {
    expect(adminMocks.revokeUserSessions).toHaveBeenCalledWith('2')
  })
})

test('无 users.write 权限时隐藏用户写操作', async () => {
  render(
    <AuthProvider
      bootstrapSession={{
        accessToken: 'token',
        refreshToken: 'refresh',
        user: { id: '1', username: 'operator', permissions: ['users.read'] },
      }}
    >
      <AdminUsersPage />
    </AuthProvider>
  )

  expect(await screen.findByText('读者')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '创建用户' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '编辑' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '撤销会话' })).not.toBeInTheDocument()
})
