import { formatFullTime, formatRelativeTime } from './time'

test('时间显示包含完整本地时间和相对时间', () => {
  const now = Date.parse('2026-07-22T08:00:00Z')

  expect(formatFullTime('2026-07-22T07:58:30Z', 'zh-CN')).toMatch(/2026/)
  expect(formatRelativeTime('2026-07-22T07:59:00Z', 'zh-CN', now)).toBe('1分钟前')
})

test('旧的无时区时间按 UTC 解析而不是按浏览器本地墙钟解析', () => {
  const now = Date.parse('2026-07-22T16:31:00Z')

  expect(formatRelativeTime('2026-07-22 16:30:00', 'zh-CN', now)).toBe('1分钟前')
})
