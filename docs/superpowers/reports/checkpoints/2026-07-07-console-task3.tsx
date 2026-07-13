import { useEffect, useState } from 'react'

import { listBookSources, type SourceRow } from '@/api/modules/sources'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'

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
      <div className="grid gap-4">
        {loading ? (
          <div className="rounded-[24px] border border-white/10 bg-black/20 p-6 text-sm text-zinc-300">Loading</div>
        ) : (
          rows.map((row) => (
            <article
              key={row.id}
              className="grid gap-4 rounded-[24px] border border-white/10 bg-black/20 p-6 text-zinc-100 shadow-[0_14px_40px_rgba(0,0,0,0.28)] md:grid-cols-[1.6fr_1fr_1fr]"
            >
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-zinc-500">Source</p>
                <h3 className="mt-3 text-2xl font-semibold text-white">{row.name}</h3>
                <p className="mt-2 text-sm text-zinc-400">Status: {row.status}</p>
              </div>
              <div className="rounded-2xl border border-white/8 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-[0.22em] text-zinc-500">Published version</p>
                <p className="mt-3 text-lg font-medium text-cyan-100">{row.publishedVersion}</p>
              </div>
              <div className="rounded-2xl border border-white/8 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-[0.22em] text-zinc-500">Latest grade</p>
                <p className="mt-3 text-lg font-medium text-emerald-200">{row.latestGrade}</p>
              </div>
            </article>
          ))
        )}
      </div>
    </ConsoleLayout>
  )
}
