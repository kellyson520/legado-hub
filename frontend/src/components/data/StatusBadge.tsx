import { useLanguage } from '@/app/providers/LanguageProvider'
import { Badge, type BadgeProps } from '@/components/ui/badge'

type StatusTone = NonNullable<BadgeProps['variant']>

const successStatuses = new Set(['accepted', 'completed', 'enabled', 'healthy', 'ok', 'passed', 'published', 'succeeded'])
const warningStatuses = new Set(['awaiting_manual_verification', 'candidate', 'degraded', 'pending', 'queued', 'running', 'scheduled'])
const failureStatuses = new Set(['blocked', 'dead', 'error', 'failed', 'rejected'])

function normalizeStatus(status: string) {
  return status.trim().toLowerCase().replace(/[\s-]+/g, '_')
}

function statusTone(status: string): StatusTone {
  if (successStatuses.has(status)) return 'success'
  if (warningStatuses.has(status)) return 'warning'
  if (failureStatuses.has(status)) return 'destructive'
  return 'secondary'
}

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const { t } = useLanguage()
  const normalized = normalizeStatus(status)
  const key = `status.${normalized}`
  const label = t(key)

  return <Badge variant={statusTone(normalized)} className={className}>{label === key ? status : label}</Badge>
}
