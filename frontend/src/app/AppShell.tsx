import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

import { AppConsoleShell } from '@/components/layout/AppConsoleShell'

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation()
  if (location.pathname === '/login') return <>{children}</>
  return <AppConsoleShell>{children}</AppConsoleShell>
}
