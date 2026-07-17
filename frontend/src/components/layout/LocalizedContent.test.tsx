import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'

import { LanguageProvider, useLanguage } from '@/app/providers/LanguageProvider'
import { LocalizedContent } from './LocalizedContent'

afterEach(() => {
  window.localStorage.clear()
})

function LocaleProbe() {
  const { setLocale } = useLanguage()
  return <button type="button" onClick={() => setLocale('en-US')}>English</button>
}

test('translates fixed text and accessibility props recursively', async () => {
  render(
    <LanguageProvider>
      <LocaleProbe />
      <LocalizedContent>
        <section>
          <h1>Inference workbench</h1>
          <button aria-label="Create user">Create user</button>
        </section>
      </LocalizedContent>
    </LanguageProvider>
  )

  expect(screen.getByRole('heading', { name: '推理工作台' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '创建用户' })).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'English' }))

  expect(await screen.findByRole('heading', { name: 'Inference workbench' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Create user' })).toBeInTheDocument()
})

test('translates legacy Chinese feature copy and raw statuses in English mode', async () => {
  render(
    <LanguageProvider>
      <LocaleProbe />
      <LocalizedContent>
        <section>
          <h1>书源运行库存</h1>
          <p>pending</p>
          <button type="button">上传 JSON 文件</button>
        </section>
      </LocalizedContent>
    </LanguageProvider>
  )

  expect(screen.getByRole('heading', { name: '书源运行库存' })).toBeInTheDocument()
  expect(screen.getByText('等待中')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'English' }))

  expect(await screen.findByRole('heading', { name: 'Source inventory' })).toBeInTheDocument()
  expect(screen.getByText('Pending')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Upload JSON file' })).toBeInTheDocument()
})
