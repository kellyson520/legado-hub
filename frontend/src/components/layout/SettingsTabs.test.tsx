import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { SettingsTabs } from './SettingsTabs'

test('settings tabs accepts registry definitions without importing a feature module', () => {
  render(
    <MemoryRouter>
      <SettingsTabs
        allTabs={[{ id: 'agents/governance', label: 'Governance' }]}
        selectedPath="agents/governance"
        settingsPath={(path) => `/settings/${path}`}
      />
    </MemoryRouter>,
  )

  expect(screen.getByRole('tab', { name: 'Governance' })).toBeInTheDocument()
})
