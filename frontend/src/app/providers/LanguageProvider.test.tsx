import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'

import { LanguageProvider, useLanguage } from './LanguageProvider'

function LocaleProbe() {
  const { locale, t, setLocale } = useLanguage()
  return (
    <div>
      <span>{locale}</span>
      <p>{t('common.loading')}</p>
      <button type="button" onClick={() => setLocale('en-US')}>English</button>
      <button type="button" onClick={() => setLocale('zh-CN')}>中文</button>
    </div>
  )
}

function InterpolatedProbe() {
  const { t } = useLanguage()
  return <span>{t('pagination.summary', { page: 2, totalPages: 4, total: 19, itemLabel: '条' })}</span>
}

afterEach(() => {
  window.localStorage.clear()
})

test('defaults to Chinese and persists a selected English locale', () => {
  render(<LanguageProvider><LocaleProbe /></LanguageProvider>)

  expect(screen.getByText('zh-CN')).toBeInTheDocument()
  expect(screen.getByText('正在加载…')).toBeInTheDocument()
  expect(document.documentElement.lang).toBe('zh-CN')

  fireEvent.click(screen.getByRole('button', { name: 'English' }))

  expect(screen.getByText('en-US')).toBeInTheDocument()
  expect(screen.getByText('Loading…')).toBeInTheDocument()
  expect(document.documentElement.lang).toBe('en-US')
  expect(window.localStorage.getItem('legado.locale')).toBe('en-US')
})

test('rejects an invalid stored locale and supports switching back to Chinese', () => {
  window.localStorage.setItem('legado.locale', 'fr-FR')
  render(<LanguageProvider><LocaleProbe /></LanguageProvider>)

  expect(screen.getByText('zh-CN')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'English' }))
  fireEvent.click(screen.getByRole('button', { name: '中文' }))

  expect(screen.getByText('zh-CN')).toBeInTheDocument()
  expect(screen.getByText('正在加载…')).toBeInTheDocument()
  expect(document.documentElement.lang).toBe('zh-CN')
  expect(window.localStorage.getItem('legado.locale')).toBe('zh-CN')
})

test('renders interpolated translation parameters', () => {
  render(<LanguageProvider><InterpolatedProbe /></LanguageProvider>)

  expect(screen.getByText('第 2 / 4 页，共 19 条')).toBeInTheDocument()
})
