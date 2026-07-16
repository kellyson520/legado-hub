import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { SystemSettingsLayout } from './SystemSettingsLayout'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/system/settings/:domain/:tab"
          element={<SystemSettingsLayout><div>Section content</div></SystemSettingsLayout>}
        />
      </Routes>
    </MemoryRouter>,
  )
}

test('deep link selects the requested Agent governance tab', () => {
  renderAt('/system/settings/agents/governance')

  expect(screen.getByRole('tab', { name: 'Evidence and governance' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByText('Section content')).toBeInTheDocument()
})
