import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  readStoredLocale,
  translate,
  type Locale,
  type TranslationParams,
} from '@/lib/i18n'

export interface LanguageContextValue {
  locale: Locale
  setLocale: (locale: Locale) => void
  toggleLocale: () => void
  t: (key: string, params?: TranslationParams) => string
}

const fallbackLanguage: LanguageContextValue = {
  locale: DEFAULT_LOCALE,
  setLocale: () => undefined,
  toggleLocale: () => undefined,
  t: (key, params) => translate(DEFAULT_LOCALE, key, params),
}

const LanguageContext = createContext<LanguageContextValue>(fallbackLanguage)

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => readStoredLocale())

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next)
    if (typeof window !== 'undefined') window.localStorage.setItem(LOCALE_STORAGE_KEY, next)
  }, [])

  const toggleLocale = useCallback(() => {
    setLocale(locale === 'zh-CN' ? 'en-US' : 'zh-CN')
  }, [locale, setLocale])

  const value = useMemo<LanguageContextValue>(() => ({
    locale,
    setLocale,
    toggleLocale,
    t: (key, params) => translate(locale, key, params),
  }), [locale, setLocale, toggleLocale])

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLanguage() {
  return useContext(LanguageContext)
}
