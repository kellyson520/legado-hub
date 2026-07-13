import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import { RunTimeline } from './RunTimeline'

test('renders a compact semantic run card', () => {
  render(<RunTimeline runs={[{ id: 'run-1', sourceVersionId: 'version-1', grade: 'A', stepResults: { parse: { elapsedMs: 18, passed: true } } }]} deployments={[]} />)

  expect(screen.getByText('run-1').closest('article')).toHaveClass('bg-card')
  expect(screen.getByText('deployment decision')).toBeInTheDocument()
})
