import { render, screen } from '@testing-library/react'

import { DetailPanel } from './DetailPanel'

test('DetailPanel renders an empty state and keyed values', () => {
  const { rerender } = render(<DetailPanel title="Details" emptyLabel="Select a row" />)
  expect(screen.getByText('Select a row')).toBeInTheDocument()

  rerender(<DetailPanel title="Details" items={[{ label: 'Status', value: 'healthy' }]} />)
  expect(screen.getByText('Status')).toBeInTheDocument()
  expect(screen.getByText('healthy')).toBeInTheDocument()
})
