import { render, screen } from '@testing-library/react'
import { AxiosError } from 'axios'

import { AuthProvider, useAuth } from '@/app/providers/AuthProvider'
import { createApiClient } from './client'

function PermissionProbe({ permission }: { permission: string }) {
  const { hasPermission } = useAuth()
  return <span>{hasPermission(permission) ? 'allowed' : 'blocked'}</span>
}

test('client retries the original request after refresh succeeds', async () => {
  let currentToken = 'stale-token'
  let attempt = 0

  const client = createApiClient({
    getAccessToken: () => currentToken,
    onRefresh: async () => {
      currentToken = 'fresh-token'
      return {
        accessToken: 'fresh-token',
        refreshToken: 'fresh-refresh',
        user: { id: '1', username: 'admin', permissions: ['dashboard.read'] },
      }
    },
    adapter: async (config) => {
      attempt += 1
      const auth =
        typeof config.headers?.get === 'function'
          ? config.headers.get('Authorization')
          : config.headers?.Authorization ?? config.headers?.authorization
      if (attempt === 1 && auth === 'Bearer stale-token') {
        throw new AxiosError(
          'expired',
          'ERR_BAD_REQUEST',
          config,
          undefined,
          {
            data: { success: false, code: 'AUTHENTICATION_ERROR', message: 'expired', data: null, meta: {}, trace_id: null },
            status: 401,
            statusText: 'Unauthorized',
            headers: {},
            config,
          }
        )
      }
      return {
        data: { success: true, code: 'OK', message: 'ok', data: { service: 'dashboard' }, meta: { page: 1 }, trace_id: null },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    },
  })

  const result = await client.get('/api/dashboard')
  expect(result.meta).toBeDefined()
  expect(attempt).toBe(2)
})

test('auth provider exposes permissions from the current user payload', async () => {
  render(
    <AuthProvider
      bootstrapSession={{
        accessToken: 'token',
        refreshToken: 'refresh',
        user: { id: '1', username: 'admin', permissions: ['engine.deploy'] },
      }}
    >
      <PermissionProbe permission="engine.deploy" />
    </AuthProvider>
  )

  expect(await screen.findByText('allowed')).toBeInTheDocument()
})

test('client unwraps patch and delete envelopes through shared methods', async () => {
  const calls: string[] = []
  const client = createApiClient({
    adapter: async (config) => {
      calls.push(`${config.method}:${config.url}`)
      return {
        data: {
          success: true,
          code: 'OK',
          message: 'ok',
          data: { id: 'row-1' },
          meta: {},
          trace_id: null,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    },
  })

  const patched = await client.patch<{ id: string }>('/api/items/row-1', { enabled: true })
  const deleted = await client.delete<{ id: string }>('/api/items/row-1')

  expect(patched.data.id).toBe('row-1')
  expect(deleted.data.id).toBe('row-1')
  expect(calls).toEqual(['patch:/api/items/row-1', 'delete:/api/items/row-1'])
})
