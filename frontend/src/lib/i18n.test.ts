import { describe, expect, it } from 'vitest'

import { errorText, roleText, statusText, translate } from './i18n'

describe('中文文案映射', () => {
  it('将运行状态和权限错误显示为中文', () => {
    expect(statusText('failed')).toBe('已失败')
    expect(errorText('FORBIDDEN')).toBe('没有执行此操作的权限')
    expect(roleText('admin')).toBe('管理员')
  })

  it('returns the equivalent English labels when requested', () => {
    expect(statusText('failed', 'en-US')).toBe('Failed')
    expect(errorText('FORBIDDEN', 'en-US')).toBe('You do not have permission to perform this action')
    expect(roleText('admin', 'en-US')).toBe('Administrator')
  })

  it('interpolates known translation keys and preserves unknown values', () => {
    expect(translate('en-US', 'pagination.summary', { page: 2, totalPages: 4, total: 19, itemLabel: 'items' })).toBe('Page 2 / 4, 19 items')
    expect(translate('zh-CN', 'server.unknown-value')).toBe('server.unknown-value')
  })
})
