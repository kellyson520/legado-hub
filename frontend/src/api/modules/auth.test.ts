import { createAuthSession } from './auth'

test('normalizes backend tokens and current identity into an auth session', () => {
  expect(
    createAuthSession(
      { access_token: 'access', refresh_token: 'refresh', permissions: ['book_sources.read'] },
      { user_id: 7, permissions: ['book_sources.read'] },
      'operator'
    )
  ).toEqual({
    accessToken: 'access',
    refreshToken: 'refresh',
    user: { id: '7', username: 'operator', permissions: ['book_sources.read'] },
  })
})
