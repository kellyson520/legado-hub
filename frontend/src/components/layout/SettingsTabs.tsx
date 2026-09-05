import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'

export interface SettingsTabItem {
  id: string
  label: ReactNode
}

export interface SettingsTabsProps {
  allTabs: SettingsTabItem[]
  selectedPath: string
  settingsPath: (path: string) => string
}

export function SettingsTabs({ allTabs, selectedPath, settingsPath }: SettingsTabsProps) {
  const navigate = useNavigate()

  return (
    <div className="rounded-md border border-border bg-card p-4 shadow-sm">
      <div className="sm:hidden">
        <label className="sr-only" htmlFor="system-settings-tab">Settings section</label>
        <select
          id="system-settings-tab"
          aria-label="Settings section"
          value={selectedPath}
          className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
          onChange={(event) => navigate(settingsPath(event.target.value))}
        >
          {allTabs.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
      </div>
      <div className="hidden overflow-x-auto sm:block">
        <div role="tablist" aria-label="Settings sections" className="flex min-w-max gap-1 border-b border-border">
          {allTabs.map((item) => {
            const selected = item.id === selectedPath
            return (
              <Link
                key={item.id}
                role="tab"
                aria-selected={selected}
                to={settingsPath(item.id)}
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
