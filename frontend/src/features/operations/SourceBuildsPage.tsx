import { useEffect, useState } from 'react'

import { listSourceBuildCandidates, type OperationSourceBuildRow } from '@/api/modules/operations'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'

function getSourceId(row: OperationSourceBuildRow) {
  return row.sourceId ?? row.source_id ?? row.payload.canonical_url ?? '-'
}

function getLatestRun(row: OperationSourceBuildRow) {
  return row.latestRun ?? row.latest_run ?? null
}

function getCreatedBy(row: OperationSourceBuildRow) {
  return row.createdBy ?? row.created_by ?? row.payload.submitted_by ?? '-'
}

function getAutonomousBuild(row: OperationSourceBuildRow) {
  return row.payload.autonomous_build as
    | {
        decision?: string
        strategy?: string
        trigger?: string
        agent_run_id?: string
        probe?: {
          search_status?: string
          toc_status?: string
          content_status?: string
          sample_title?: string
          failure_reason?: string
        }
        validation?: {
          grade?: string
          quality_score?: number
        }
      }
    | undefined
}

export function SourceBuildsPage() {
  const [rows, setRows] = useState<OperationSourceBuildRow[]>([])

  useEffect(() => {
    let mounted = true

    async function load() {
      const response = await listSourceBuildCandidates()
      if (!mounted) return
      setRows(response.data)
    }

    void load()
    return () => {
      mounted = false
    }
  }, [])

  return (
    <ConsoleLayout
      eyebrow="Operations"
      title="Source build candidates"
      description="查看候选 source build、最近验证结果与自动修补探针摘要。"
    >
      <div className="overflow-hidden rounded-2xl border border-border bg-card">
        <table className="min-w-full divide-y divide-border text-sm">
          <thead className="bg-muted/40 text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Source</th>
              <th className="px-4 py-3 font-medium">Keyword</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Latest grade</th>
              <th className="px-4 py-3 font-medium">Automation</th>
              <th className="px-4 py-3 font-medium">Submitted by</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => {
              const latestRun = getLatestRun(row)
              const autonomousBuild = getAutonomousBuild(row)
              return (
                <tr key={row.id}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-foreground">{getSourceId(row)}</div>
                    <div className="text-xs text-muted-foreground">{row.id}</div>
                  </td>
                  <td className="px-4 py-3">{row.payload.keyword || '-'}</td>
                  <td className="px-4 py-3">{row.status}</td>
                  <td className="px-4 py-3">{latestRun?.grade ?? '-'}</td>
                  <td className="px-4 py-3">
                    {autonomousBuild ? (
                      <>
                        <div>{autonomousBuild.decision ?? '-'}</div>
                        <div className="text-xs text-muted-foreground">
                          {autonomousBuild.trigger ?? '-'} 路 {autonomousBuild.strategy ?? '-'}
                        </div>
                        {autonomousBuild.validation ? (
                          <div className="text-xs text-muted-foreground">
                            validation: {autonomousBuild.validation.grade ?? '-'} (
                            {autonomousBuild.validation.quality_score ?? '-'}
                            )
                          </div>
                        ) : null}
                        {autonomousBuild.probe ? (
                          <>
                            <div className="text-xs text-muted-foreground">
                              search/toc/content: {autonomousBuild.probe.search_status ?? '-'} /{' '}
                              {autonomousBuild.probe.toc_status ?? '-'} / {autonomousBuild.probe.content_status ?? '-'}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {autonomousBuild.probe.sample_title ??
                                autonomousBuild.probe.failure_reason ??
                                '-'}
                            </div>
                          </>
                        ) : null}
                      </>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{getCreatedBy(row)}</td>
                </tr>
              )
            })}
            {rows.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-muted-foreground" colSpan={6}>
                  No source build candidates yet
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </ConsoleLayout>
  )
}
