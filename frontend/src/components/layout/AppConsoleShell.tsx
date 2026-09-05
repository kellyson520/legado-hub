import { useState, type ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { ChevronLeft, LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Sun, Monitor, X } from 'lucide-react'

import { consoleMark, findNavigationItem, navigationGroups } from '@/app/navigation'
import { useAuth } from '@/app/providers/AuthProvider'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { useTheme, type ThemeMode } from '@/app/providers/ThemeProvider'
import { Button } from '@/components/ui/button'
import { LanguageToggle } from '@/components/layout/LanguageToggle'
import { cn } from '@/lib/utils'

function Navigation({ collapsed, closeMobile }: { collapsed?: boolean; closeMobile?: () => void }) {
  const { hasPermission, isAdmin } = useAuth()
  const { t } = useLanguage()
  const location = useLocation()

  return (
    <nav aria-label={t('shell.navigation')} className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
      {navigationGroups.map((group) => {
        const items = group.items.filter((item) => hasPermission(item.permission) && (!item.adminOnly || isAdmin))
        if (!items.length) return null
        return (
          <section key={group.labelKey} className="space-y-1">
            {!collapsed ? <p className="px-2 pb-1 text-[11px] font-semibold text-muted-foreground">{t(group.labelKey)}</p> : null}
            {items.map(({ icon: Icon, labelKey, to }) => {
              const label = t(labelKey)
              return (
              <NavLink
                key={to}
                to={to}
                end={to === '/sources'}
                onClick={closeMobile}
                title={collapsed ? label : undefined}
                className={({ isActive }) => cn(
                  'flex h-10 items-center gap-3 rounded-md px-2.5 text-sm font-medium transition-colors',
                  collapsed && 'justify-center px-0',
                  isActive || (to === '/sources/health' && location.pathname.startsWith('/sources/health'))
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                )}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                {!collapsed ? <span>{label}</span> : null}
              </NavLink>
              )
            })}
          </section>
        )
      })}
    </nav>
  )
}

function ThemeControl() {
  const { mode, setMode } = useTheme()
  const { t } = useLanguage()
  const options: Array<{ mode: ThemeMode; label: string; icon: typeof Sun }> = [
    { mode: 'light', label: t('theme.light'), icon: Sun },
    { mode: 'dark', label: t('theme.dark'), icon: Moon },
    { mode: 'system', label: t('theme.system'), icon: Monitor },
  ]
  return (
    <div aria-label={t('theme.label')} className="hidden items-center rounded-md border border-border bg-muted p-0.5 sm:flex">
      {options.map(({ mode: option, label, icon: Icon }) => (
        <button
          key={option}
          type="button"
          title={label}
          aria-label={label}
          aria-pressed={mode === option}
          onClick={() => setMode(option)}
          className={cn('grid h-7 w-7 place-items-center rounded-[3px] text-muted-foreground', mode === option && 'bg-card text-foreground shadow-sm')}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      ))}
    </div>
  )
}

export function AppConsoleShell({ children }: { children: ReactNode }) {
  const { session, logout } = useAuth()
  const { t } = useLanguage()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const CurrentMark = consoleMark
  const current = findNavigationItem(location.pathname)

  return (
    <div className="min-h-screen bg-background text-foreground">
      <aside className={cn('fixed inset-y-0 left-0 z-30 hidden border-r border-border bg-card lg:flex lg:flex-col', collapsed ? 'w-[72px]' : 'w-[248px]')}>
        <div className={cn('flex h-16 items-center border-b border-border px-4', collapsed ? 'justify-center' : 'justify-between')}>
          <Link to="/sources" className="flex items-center gap-2 overflow-hidden font-semibold text-foreground">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-primary text-primary-foreground"><CurrentMark className="h-4 w-4" /></span>
            {!collapsed ? <span className="whitespace-nowrap">Legado Hub</span> : null}
          </Link>
          {!collapsed ? <Button variant="ghost" size="icon" title={t('shell.collapseSidebar')} aria-label={t('shell.collapseSidebar')} onClick={() => setCollapsed(true)}><PanelLeftClose className="h-4 w-4" /></Button> : null}
        </div>
        {collapsed ? <Button variant="ghost" size="icon" title={t('shell.expandSidebar')} aria-label={t('shell.expandSidebar')} className="mx-auto mt-3" onClick={() => setCollapsed(false)}><PanelLeftOpen className="h-4 w-4" /></Button> : null}
        <Navigation collapsed={collapsed} />
        {!collapsed ? <p className="border-t border-border px-5 py-3 text-[11px] text-muted-foreground">{t('shell.legadoControl')}</p> : null}
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label={t('shell.navigation')}>
          <button aria-label={t('shell.closeNavigationOverlay')} className="absolute inset-0 cursor-default bg-black/45" onClick={() => setMobileOpen(false)} />
          <aside className="relative flex h-full w-[280px] flex-col border-r border-border bg-card shadow-2xl">
            <div className="flex h-16 items-center justify-between border-b border-border px-4">
              <span className="flex items-center gap-2 font-semibold"><span className="grid h-8 w-8 place-items-center rounded-md bg-primary text-primary-foreground"><CurrentMark className="h-4 w-4" /></span>Legado Hub</span>
              <Button variant="ghost" size="icon" aria-label={t('shell.closeNavigation')} onClick={() => setMobileOpen(false)}><X className="h-4 w-4" /></Button>
            </div>
            <Navigation closeMobile={() => setMobileOpen(false)} />
          </aside>
        </div>
      ) : null}

      <div className={cn('min-h-screen transition-[padding] lg:pl-[248px]', collapsed && 'lg:pl-[72px]')}>
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <Button variant="ghost" size="icon" className="lg:hidden" aria-label={t('shell.openNavigation')} onClick={() => setMobileOpen(true)}><Menu className="h-5 w-5" /></Button>
            <div className="min-w-0">
              <p className="text-[11px] font-medium text-muted-foreground">{t('shell.console')} / {current ? t(current.labelKey) : t('shell.overview')}</p>
              <p className="truncate text-sm font-semibold text-foreground">{current ? t(current.labelKey) : 'Legado Hub'}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 text-xs text-muted-foreground md:flex"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />{t('shell.apiOnline')}</span>
            <ThemeControl />
            <LanguageToggle className="hidden sm:inline-flex" />
            <div className="ml-1 flex items-center gap-2 border-l border-border pl-3">
              <span className="hidden text-right text-xs leading-4 sm:block"><span className="block font-medium text-foreground">{session?.user.username ?? t('shell.account')}</span><span className="text-muted-foreground">{t('shell.signedIn')}</span></span>
              <Button variant="ghost" size="icon" aria-label={t('shell.signOut')} title={t('shell.signOut')} onClick={() => void logout()}><LogOut className="h-4 w-4" /></Button>
            </div>
          </div>
        </header>
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  )
}
