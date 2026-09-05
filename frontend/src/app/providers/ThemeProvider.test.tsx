import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'

import { ThemeProvider, useTheme } from './ThemeProvider'

function ThemeProbe() {
  const { mode, resolved, setMode } = useTheme()
  return (
    <div>
      <span>{`${mode}:${resolved}`}</span>
      <button onClick={() => setMode('light')}>Set light</button>
    </div>
  )
}

afterEach(() => {
  window.localStorage.clear()
  document.documentElement.className = ''
})

test('persists a selected theme mode and applies its resolved class', async () => {
  render(<ThemeProvider><ThemeProbe /></ThemeProvider>)

  fireEvent.click(screen.getByRole('button', { name: 'Set light' }))

  expect(document.documentElement).toHaveClass('light')
  expect(document.documentElement).not.toHaveClass('dark')
  expect(window.localStorage.getItem('legado.theme-mode')).toBe('light')
  expect(screen.getByText('light:light')).toBeInTheDocument()
})
