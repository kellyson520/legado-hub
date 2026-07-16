import type { EvidenceCitation } from '@/api/modules/novelAnalysis'

export function EvidenceDrawer({ evidence }: { evidence: EvidenceCitation | null }) {
  return <aside className="rounded-md border border-border bg-card p-5 shadow-sm" aria-live="polite">
    <h2 className="text-lg font-semibold">Evidence excerpt</h2>
    {evidence ? <>
      <p className="mt-3 text-sm font-medium">{evidence.canonical_chapter_title}</p>
      <p className="mt-1 font-mono text-[11px] text-muted-foreground">{evidence.content_sha256}</p>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{evidence.excerpt}</p>
    </> : <p className="mt-3 text-sm text-muted-foreground">Select a claim to inspect its exact citation.</p>}
  </aside>
}
