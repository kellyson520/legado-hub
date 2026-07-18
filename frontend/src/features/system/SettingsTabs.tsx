import { Link, useNavigate } from 'react-router-dom'

import type { SettingsDomainDefinition, SettingsTabDefinition } from './settingsRegistry'
import { SETTINGS_DOMAINS, settingsPath } from './settingsRegistry'

export interface SettingsTabsProps {
  domain: SettingsDomainDefinition
  tab: SettingsTabDefinition
}

export function SettingsTabs({ domain, tab }: SettingsTabsProps) {
  const navigate = useNavigate()

  return (
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
  )
}
