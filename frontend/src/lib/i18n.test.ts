import { describe, expect, it } from 'vitest'

import { errorText, roleText, statusText } from './i18n'

describe('中文文案映射', () => {
  it('将运行状态和权限错误显示为中文', () => {
    expect(statusText('failed')).toBe('已失败')
    expect(errorText('FORBIDDEN')).toBe('没有执行此操作的权限')
    expect(roleText('admin')).toBe('管理员')
  })
})
