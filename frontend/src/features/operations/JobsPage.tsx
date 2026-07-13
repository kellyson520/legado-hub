import { useEffect, useState } from 'react'

import { listOperationsJobs, type OperationJobRow } from '@/api/modules/operations'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'

export function JobsPage() {
  const [jobs, setJobs] = useState<OperationJobRow[]>([])

  useEffect(() => {
    let mounted = true

    async function load() {
      const response = await listOperationsJobs()
      if (!mounted) return
      setJobs(response.data)
    }

    load()
    return () => {
      mounted = false
    }
  }, [])

  return (
    <ConsoleLayout
      eyebrow="Operations"
      title="Jobs control plane"
      description="集中查看后台 durable jobs 的状态、租约尝试和失败信息，为后续 webhook / SSE 分发与运营排障提供统一入口。"
    >
      <div className="overflow-hidden rounded-2xl border border-border bg-card">
        <table className="min-w-full divide-y divide-border text-sm">
          <thead className="bg-muted/40 text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Kind</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Tenant</th>
              <th className="px-4 py-3 font-medium">Attempts</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {jobs.map((job) => (
              <tr key={job.id}>
                <td className="px-4 py-3">{job.kind}</td>
                <td className="px-4 py-3">{job.status}</td>
                <td className="px-4 py-3">{job.tenantId ?? job.tenant_id ?? '-'}</td>
                <td className="px-4 py-3">{job.attemptCount ?? job.attempt_count ?? 0}</td>
              </tr>
            ))}
            {jobs.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-muted-foreground" colSpan={4}>
                  No operations jobs yet
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </ConsoleLayout>
  )
}
