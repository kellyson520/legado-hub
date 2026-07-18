import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { findSettingsDomain, SETTINGS_DOMAINS, settingsPath } from './settingsRegistry'
import { SettingsTabs } from './SettingsTabs'

export function SystemSettingsLayout({ children }: { children: ReactNode }) {
  const { domain: requestedDomain, tab: requestedTab } = useParams()
  const domain = findSettingsDomain(requestedDomain) ?? SETTINGS_DOMAINS[0]
  const tab = domain.tabs.find((item) => item.id === requestedTab) ?? domain.tabs[0]

  return (
    <ConsolePageShell
      eyebrow="System"
      title="Settings directory"
      description="按领域管理模型、Agent、书源与运行策略。每个页面独立保存，避免无关配置相互覆盖。"
    >
      <div className="grid gap-5 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <nav aria-label="Settings domains" className="rounded-md border border-border bg-card p-2 shadow-sm">
          <p className="px-3 pb-2 pt-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Domains
          </p>
          <div className="space-y-1">
            {SETTINGS_DOMAINS.map((item) => {
              const firstTab = item.tabs[0]
              const selected = item.id === domain.id
              return (
                <Link
                  key={item.id}
                  to={settingsPath(item.id, firstTab.id)}
                  aria-current={selected ? 'page' : undefined}
                  className={selected
                    ? 'block rounded-sm bg-primary px-3 py-2 text-sm font-medium text-primary-foreground'
                    : 'block rounded-sm px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground'}
                >
                  {item.label}
                </Link>
              )
            })}
          </div>
        </nav>

        <section className="min-w-0 space-y-4">
          <SettingsTabs domain={domain} tab={tab} />
          <div role="tabpanel" aria-label={tab.label}>{children}</div>
        </section>
      </div>
    </ConsolePageShell>
  )
}
