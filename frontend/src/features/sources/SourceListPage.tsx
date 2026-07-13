import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { listBookSources, type SourceRow } from '@/api/modules/sources'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Card } from '@/components/ui/card'

export function SourceListPage() {
  const [rows, setRows] = useState<SourceRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true

    async function load() {
      const response = await listBookSources({ page: 1, page_size: 20 })
      if (!mounted) return
      setRows(response.data)
      setLoading(false)
    }

    load()
    return () => {
      mounted = false
    }
  }, [])

  return (
    <ConsoleLayout
      eyebrow="Sources"
      title="Runtime source inventory"
      description="查看当前已发布源、版本状态与最近一轮运行评分，后续这里会继续挂接回归、诊断、回滚与替换决策。"
    >
      <div className="flex justify-end">
        <Link
          to="/sources/health"
          className="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90"
        >
          Open source health control plane
        </Link>
      </div>
      <div className="grid gap-4">
        {loading ? (
          <Card className="p-6 text-sm text-muted-foreground">
            Loading
          </Card>
        ) : (
          rows.map((row) => (
            <Card
              key={row.id}
              className="grid gap-4 p-5 md:grid-cols-[1.6fr_1fr_1fr]"
            >
              <div>
                <p className="text-xs font-medium text-muted-foreground">Source</p>
                <h3 className="mt-2 text-lg font-semibold text-foreground">{row.name}</h3>
                <p className="mt-2 text-sm text-muted-foreground">Status: {row.status}</p>
              </div>
              <div className="rounded-md border border-border bg-muted/40 p-4">
                <p className="text-xs font-medium text-muted-foreground">Published version</p>
                <p className="mt-2 text-lg font-medium text-primary">{row.publishedVersion}</p>
              </div>
              <div className="rounded-md border border-border bg-muted/40 p-4">
                <p className="text-xs font-medium text-muted-foreground">Latest grade</p>
                <p className="mt-2 text-lg font-medium text-emerald-600 dark:text-emerald-400">{row.latestGrade}</p>
              </div>
            </Card>
          ))
        )}
      </div>
    </ConsoleLayout>
  )
}
