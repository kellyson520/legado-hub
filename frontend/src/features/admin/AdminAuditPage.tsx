import { useEffect, useState } from 'react'

import { listAuditLogs, type AuditLogRow } from '@/api/modules/admin'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'

export function AdminAuditPage() {
  const [logs, setLogs] = useState<AuditLogRow[]>([])

  useEffect(() => {
    let mounted = true

    async function load() {
      const response = await listAuditLogs()
      if (!mounted) return
      setLogs(response.data)
    }

    load()
    return () => {
      mounted = false
    }
  }, [])

  return (
    <ConsoleLayout
      eyebrow="Audit"
      title="Operational trace ledger"
      description="把高风险操作与自动化动作都纳入统一审计视图，便于排查部署、回滚、授权与任务执行链路。"
    >
      <div className="space-y-3">
        {logs.length === 0 ? (
          <div className="rounded-md border border-dashed border-border bg-muted/30 p-6 text-sm text-muted-foreground">
            No audit rows loaded yet.
          </div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className="rounded-md border border-border bg-card p-4 shadow-sm">
              <p className="text-sm font-medium text-foreground">
                {log.action} / {log.resource}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">{log.detail}</p>
            </div>
          ))
        )}
      </div>
    </ConsoleLayout>
  )
}
