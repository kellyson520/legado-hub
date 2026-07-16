import type { ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { findSettingsDomain, SETTINGS_DOMAINS, settingsPath } from './settingsRegistry'

export function SystemSettingsLayout({ children }: { children: ReactNode }) {
  const { domain: requestedDomain, tab: requestedTab } = useParams()
  const navigate = useNavigate()
  const domain = findSettingsDomain(requestedDomain) ?? SETTINGS_DOMAINS[0]
  const tab = domain.tabs.find((item) => item.id === requestedTab) ?? domain.tabs[0]

  return (
    <ConsoleLayout
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
          <div className="rounded-md border border-border bg-card p-4 shadow-sm">
            <div className="sm:hidden">
              <label className="sr-only" htmlFor="system-settings-tab">Settings section</label>
              <select
                id="system-settings-tab"
                aria-label="Settings section"
                value={`${domain.id}/${tab.id}`}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
                onChange={(event) => {
                  const [nextDomain, nextTab] = event.target.value.split('/')
                  navigate(settingsPath(nextDomain, nextTab))
                }}
              >
                {SETTINGS_DOMAINS.flatMap((item) => item.tabs.map((itemTab) => (
                  <option key={`${item.id}/${itemTab.id}`} value={`${item.id}/${itemTab.id}`}>
                    {item.label} · {itemTab.label}
                  </option>
                )))}
              </select>
            </div>
            <div className="hidden overflow-x-auto sm:block">
              <div role="tablist" aria-label={`${domain.label} sections`} className="flex min-w-max gap-1 border-b border-border">
                {domain.tabs.map((item) => {
                  const selected = item.id === tab.id
                  return (
                    <Link
                      key={item.id}
                      role="tab"
                      aria-selected={selected}
                      to={settingsPath(domain.id, item.id)}
                      className={selected
                        ? 'border-b-2 border-primary px-3 py-2 text-sm font-semibold text-foreground'
                        : 'border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground'}
                    >
                      {item.label}
                    </Link>
                  )
                })}
              </div>
            </div>
          </div>
          <div role="tabpanel" aria-label={tab.label}>{children}</div>
        </section>
      </div>
    </ConsoleLayout>
  )
}
