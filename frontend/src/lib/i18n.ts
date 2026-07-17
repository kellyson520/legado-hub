export type Locale = 'zh-CN' | 'en-US'
export type TranslationParams = Record<string, string | number>

export const DEFAULT_LOCALE: Locale = 'zh-CN'
export const LOCALE_STORAGE_KEY = 'legado.locale'

const catalogs: Record<Locale, Record<string, string>> = {
  'zh-CN': {
    'common.loading': '正在加载…',
    'common.search': '搜索',
    'common.clear': '清空',
    'common.retry': '重试',
    'common.previous': '上一页',
    'common.next': '下一页',
    'common.items': '条',
    'common.noResults': '暂无匹配数据',
    'common.save': '保存',
    'common.cancel': '取消',
    'common.close': '关闭',
    'common.confirm': '确认',
    'common.enabled': '已启用',
    'common.disabled': '已停用',
    'common.language': '语言',
    'common.chinese': '中文',
    'common.english': 'English',
    'pagination.summary': '第 {page} / {totalPages} 页，共 {total} {itemLabel}',
    'status.pending': '等待中',
    'status.running': '运行中',
    'status.succeeded': '已成功',
    'status.failed': '已失败',
    'status.enabled': '已启用',
    'status.disabled': '已停用',
    'status.candidate': '候选',
    'status.published': '已发布',
    'status.unknown': '未知',
    'error.FORBIDDEN': '没有执行此操作的权限',
    'error.AUTHENTICATION_ERROR': '登录状态无效或已过期',
    'error.NOT_FOUND': '未找到对应资源',
    'error.VALIDATION_ERROR': '提交的数据不符合要求',
    'error.generic': '操作失败，请稍后重试',
    'role.admin': '管理员',
    'role.user': '普通用户',
  },
  'en-US': {
    'common.loading': 'Loading…',
    'common.search': 'Search',
    'common.clear': 'Clear',
    'common.retry': 'Retry',
    'common.previous': 'Previous',
    'common.next': 'Next',
    'common.items': 'items',
    'common.noResults': 'No matching data',
    'common.save': 'Save',
    'common.cancel': 'Cancel',
    'common.close': 'Close',
    'common.confirm': 'Confirm',
    'common.enabled': 'Enabled',
    'common.disabled': 'Disabled',
    'common.language': 'Language',
    'common.chinese': '中文',
    'common.english': 'English',
    'pagination.summary': 'Page {page} / {totalPages}, {total} {itemLabel}',
    'status.pending': 'Pending',
    'status.running': 'Running',
    'status.succeeded': 'Succeeded',
    'status.failed': 'Failed',
    'status.enabled': 'Enabled',
    'status.disabled': 'Disabled',
    'status.candidate': 'Candidate',
    'status.published': 'Published',
    'status.unknown': 'Unknown',
    'error.FORBIDDEN': 'You do not have permission to perform this action',
    'error.AUTHENTICATION_ERROR': 'Your session is invalid or has expired',
    'error.NOT_FOUND': 'The requested resource was not found',
    'error.VALIDATION_ERROR': 'The submitted data is invalid',
    'error.generic': 'The operation failed. Please try again later',
    'role.admin': 'Administrator',
    'role.user': 'User',
  },
}

const statusKeys: Record<string, string> = {
  pending: 'status.pending',
  running: 'status.running',
  succeeded: 'status.succeeded',
  failed: 'status.failed',
  enabled: 'status.enabled',
  disabled: 'status.disabled',
  candidate: 'status.candidate',
  published: 'status.published',
  unknown: 'status.unknown',
}

const errorKeys: Record<string, string> = {
  FORBIDDEN: 'error.FORBIDDEN',
  AUTHENTICATION_ERROR: 'error.AUTHENTICATION_ERROR',
  NOT_FOUND: 'error.NOT_FOUND',
  VALIDATION_ERROR: 'error.VALIDATION_ERROR',
}

const roleKeys: Record<string, string> = {
  admin: 'role.admin',
  user: 'role.user',
}

function interpolate(template: string, params: TranslationParams = {}) {
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (match, name: string) => (
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match
  ))
}

export function translate(locale: Locale, key: string, params: TranslationParams = {}) {
  const value = catalogs[locale][key] ?? catalogs['en-US'][key] ?? key
  return interpolate(value, params)
}

export const statusText = (value: string, locale: Locale = DEFAULT_LOCALE) => {
  const key = statusKeys[value]
  return key ? translate(locale, key) : value
}

export const errorText = (value: string, locale: Locale = DEFAULT_LOCALE) => {
  const key = errorKeys[value]
  return key ? translate(locale, key) : translate(locale, 'error.generic')
}

export const roleText = (value: string, locale: Locale = DEFAULT_LOCALE) => {
  const key = roleKeys[value]
  return key ? translate(locale, key) : value
}

export function isLocale(value: string | null | undefined): value is Locale {
  return value === 'zh-CN' || value === 'en-US'
}

export function readStoredLocale(storage: Storage | undefined = typeof window === 'undefined' ? undefined : window.localStorage): Locale {
  const value = storage?.getItem(LOCALE_STORAGE_KEY)
  return isLocale(value) ? value : DEFAULT_LOCALE
}
