import { render, screen } from '@testing-library/react'

import { SettingsEffectiveStatus } from './SettingsEffectiveStatus'

test('renders a stable fallback when settings have not been saved', () => {
  render(<SettingsEffectiveStatus updatedAt={null} />)

  expect(screen.getByRole('status')).toHaveTextContent('Effective after the first save')
})

test('formats the server update timestamp as an accessible status', () => {
  render(<SettingsEffectiveStatus updatedAt="2026-07-17T08:30:00.000Z" />)

  expect(screen.getByRole('status')).toHaveTextContent(/^Effective /)
})
