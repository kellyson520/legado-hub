import type { ReactNode } from 'react'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { LocalizedContent } from '@/components/layout/LocalizedContent'

export function ConsoleLayout({
  eyebrow,
  title,
  description,
  actions,
  children,
}: {
  eyebrow: string
  title: string
  description: string
  actions?: ReactNode
  children: ReactNode
}) {
  const { t } = useLanguage()
  return (
    <section className="mx-auto w-full max-w-[1440px] space-y-5 px-4 py-5 lg:px-8 lg:py-7">
      <header className="flex flex-col gap-4 border-b border-border pb-5 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-primary">{t(eyebrow)}</p>
          <h1 className="mt-2 text-2xl font-semibold text-foreground">{t(title)}</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{t(description)}</p>
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2"><LocalizedContent>{actions}</LocalizedContent></div> : null}
      </header>
      <LocalizedContent>{children}</LocalizedContent>
    </section>
  )
}
