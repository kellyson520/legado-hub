import type { EvidenceCitation } from '@/api/modules/novelAnalysis'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { DetailPanel } from '@/components/detail/DetailPanel'

export function EvidenceDrawer({ evidence }: { evidence: EvidenceCitation | null }) {
  const { t } = useLanguage()
  return <DetailPanel title={t('analysis.evidenceExcerpt')} emptyLabel={t('No evidence selected')} className="shadow-sm">
    {evidence ? <>
      <p className="mt-3 text-sm font-medium">{evidence.canonical_chapter_title}</p>
      <p className="mt-1 font-mono text-[11px] text-muted-foreground">{evidence.content_sha256}</p>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{evidence.excerpt}</p>
    </> : null}
  </DetailPanel>
}
