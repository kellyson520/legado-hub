import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemeMode = 'light' | 'dark' | 'system'
type ResolvedTheme = Exclude<ThemeMode, 'system'>

interface ThemeContextValue {
  mode: ThemeMode
  resolved: ResolvedTheme
  setMode: (mode: ThemeMode) => void
}

const STORAGE_KEY = 'legado.theme-mode'
const ThemeContext = createContext<ThemeContextValue | null>(null)

function isThemeMode(value: string | null): value is ThemeMode {
  return value === 'light' || value === 'dark' || value === 'system'
}

function readStoredTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'system'
  const value = window.localStorage.getItem(STORAGE_KEY)
  return isThemeMode(value) ? value : 'system'
}

function systemTheme(): ResolvedTheme {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function initialResolvedTheme(): ResolvedTheme {
  const mode = readStoredTheme()
  return mode === 'system' ? systemTheme() : mode
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(readStoredTheme)
  const [resolved, setResolved] = useState<ResolvedTheme>(initialResolvedTheme)

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') {
      setResolved(mode === 'dark' ? 'dark' : 'light')
      return
    }
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const updateResolved = () => setResolved(mode === 'system' ? (query.matches ? 'dark' : 'light') : mode)
    updateResolved()
    query.addEventListener('change', updateResolved)
    return () => query.removeEventListener('change', updateResolved)
  }, [mode])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolved === 'dark')
    document.documentElement.classList.toggle('light', resolved === 'light')
    window.localStorage.setItem(STORAGE_KEY, mode)
  }, [mode, resolved])

  const value = useMemo(() => ({ mode, resolved, setMode }), [mode, resolved])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme must be used within ThemeProvider')
  return context
}
