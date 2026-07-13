const statuses: Record<string, string> = { pending: '等待中', running: '运行中', succeeded: '已成功', failed: '已失败', enabled: '已启用', disabled: '已停用' }
const errors: Record<string, string> = { FORBIDDEN: '没有执行此操作的权限', AUTHENTICATION_ERROR: '登录状态无效或已过期', NOT_FOUND: '未找到对应资源', VALIDATION_ERROR: '提交的数据不符合要求' }
const roles: Record<string, string> = { admin: '管理员', user: '普通用户' }
export const statusText = (value: string) => statuses[value] ?? value
export const errorText = (value: string) => errors[value] ?? '操作失败，请稍后重试'
export const roleText = (value: string) => roles[value] ?? value
