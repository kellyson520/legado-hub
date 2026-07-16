import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { getEvidence, getWorkSnapshot, type EvidenceCitation, type WorkSnapshot } from '@/api/modules/novelAnalysis'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'

export function WorkAnalysisPage() {
  const { workId = '' } = useParams()
  const [snapshot, setSnapshot] = useState<WorkSnapshot | null>(null)
  const [evidence, setEvidence] = useState<EvidenceCitation | null>(null)

  useEffect(() => { void getWorkSnapshot(workId).then((response) => setSnapshot(response.data)) }, [workId])
  async function openEvidence(evidenceId: string) { setEvidence((await getEvidence(evidenceId)).data) }

  return <ConsoleLayout eyebrow="Novel analysis" title="Evidence-backed work analysis" description="人物、关系、事件与世界观结论均可回到精确正文片段。">
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <section className="rounded-md border border-border bg-card p-5 shadow-sm"><h2 className="text-lg font-semibold">Published claims</h2><div className="mt-4 space-y-2">{snapshot?.published_claims.map((claim) => <Button key={claim.id} variant="outline" className="h-auto w-full justify-start whitespace-normal text-left" onClick={() => void openEvidence(claim.evidence_ids[0])}>{claim.subject_entity_id} · {claim.predicate}</Button>)}</div><h2 className="mt-6 text-lg font-semibold">Open conflicts</h2><div className="mt-3 text-sm text-muted-foreground">{snapshot?.open_conflicts.length ?? 0} awaiting adjudication</div></section>
      <aside className="rounded-md border border-border bg-card p-5 shadow-sm"><h2 className="text-lg font-semibold">Evidence excerpt</h2>{evidence ? <><p className="mt-3 text-sm font-medium">{evidence.canonical_chapter_title}</p><p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{evidence.excerpt}</p></> : <p className="mt-3 text-sm text-muted-foreground">Select a published claim to inspect its citation.</p>}</aside>
    </div>
  </ConsoleLayout>
}
