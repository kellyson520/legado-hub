import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

const apiKeysMocks = vi.hoisted(() => ({
  listApiKeys: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{ id: 1, name: 'reader', permissions: ['read.work'], is_enabled: true }],
    meta: { total: 1 },
    trace_id: null,
  }),
  createApiKey: vi.fn(),
  disableApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
}))

vi.mock('@/api/modules/admin', () => apiKeysMocks)

import { AuthProvider } from '@/app/providers/AuthProvider'
import { ApiKeysPage } from './ApiKeysPage'

test('只读 API Key 管理员看不到写操作控件', async () => {
  render(
    <AuthProvider
      bootstrapSession={{
        accessToken: 'token',
        refreshToken: 'refresh',
        user: { id: '1', username: 'reader', permissions: ['api_keys.read'] },
      }}
    >
      <ApiKeysPage />
    </AuthProvider>
  )

  expect(await screen.findByText('reader')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '创建密钥' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '禁用' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /删除 reader/ })).not.toBeInTheDocument()
})
