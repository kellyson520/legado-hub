export type TimeLocale = 'zh-CN' | 'en-US'

function normalizeTimestamp(value: string | number | Date): string | number | Date {
  if (typeof value !== 'string') return value
  const trimmed = value.trim()
  if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(trimmed)) {
    return `${trimmed.replace(' ', 'T')}Z`
  }
  if (/^\d{4}-\d{2}-\d{2}T.*$/.test(trimmed) && !/(?:Z|[+-]\d{2}:?\d{2})$/.test(trimmed)) {
    return `${trimmed}Z`
  }
  return trimmed
}

export function parseTimestamp(value: string | number | Date): Date | null {
  const date = new Date(normalizeTimestamp(value))
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatFullTime(value: string | number | Date, locale: TimeLocale): string {
  const date = parseTimestamp(value)
  if (!date) return locale === 'en-US' ? 'Unknown time' : '时间未知'
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date)
}

export function formatRelativeTime(value: string | number | Date, locale: TimeLocale, now = Date.now()): string {
  const date = parseTimestamp(value)
  if (!date) return locale === 'en-US' ? 'Just now' : '刚刚'
  const elapsedSeconds = Math.max(0, Math.floor((now - date.getTime()) / 1000))
  if (elapsedSeconds < 60) return locale === 'en-US' ? 'Just now' : '刚刚'
  const minutes = Math.floor(elapsedSeconds / 60)
  if (minutes < 60) return locale === 'en-US' ? `${minutes}m ago` : `${minutes}分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return locale === 'en-US' ? `${hours}h ago` : `${hours}小时前`
  const days = Math.floor(hours / 24)
  if (days < 7) return locale === 'en-US' ? `${days}d ago` : `${days}天前`
  return formatFullTime(date, locale)
}
