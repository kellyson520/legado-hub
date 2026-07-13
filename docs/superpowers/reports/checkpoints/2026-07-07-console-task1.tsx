import type { ReactNode } from 'react'

export function AppShell({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-[#090b10] text-zinc-100">{children}</div>
}
