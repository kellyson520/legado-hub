import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import { LanguageProvider, useLanguage } from '@/app/providers/LanguageProvider'
import { RunTimeline } from './RunTimeline'

test('renders a compact semantic run card', () => {
  render(<RunTimeline runs={[{ id: 'run-1', sourceVersionId: 'version-1', grade: 'A', stepResults: { parse: { elapsedMs: 18, passed: true } } }]} deployments={[]} />)

  expect(screen.getByText('run-1').closest('article')).toHaveClass('bg-card')
  expect(screen.getByText('部署决策')).toBeInTheDocument()
})

test('translates fixed run labels with the active locale', async () => {
  function LocaleProbe() {
    const { setLocale } = useLanguage()
    return <button type="button" onClick={() => setLocale('en-US')}>English</button>
  }

  render(
    <LanguageProvider>
      <LocaleProbe />
      <RunTimeline runs={[{ id: 'run-1', sourceVersionId: 'version-1', grade: 'A', stepResults: { parse: { elapsedMs: 18, passed: true } } }]} deployments={[]} />
    </LanguageProvider>
  )

  fireEvent.click(screen.getByRole('button', { name: 'English' }))
  expect(await screen.findByText('Deployment decision')).toBeInTheDocument()
  expect(await screen.findByText('Waiting for deployment review')).toBeInTheDocument()
})
