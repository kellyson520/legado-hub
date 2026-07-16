import { render, screen } from '@testing-library/react'

import { StatusMessage } from './StatusMessage'

test('renders success feedback as a status message', () => {
  render(<StatusMessage tone="success" message="Saved" />)

  expect(screen.getByRole('status')).toHaveClass('text-emerald-600')
  expect(screen.getByText('Saved')).toBeInTheDocument()
})

test('renders error feedback as an alert and supports an inline element', () => {
  render(<StatusMessage tone="error" message="Failed" as="span" className="mt-3" />)

  expect(screen.getByRole('alert')).toHaveClass('text-destructive', 'mt-3')
  expect(screen.getByText('Failed')).toBeInTheDocument()
  expect(screen.getByRole('alert').tagName).toBe('SPAN')
})

test('does not render when feedback is empty', () => {
  const { container } = render(<StatusMessage tone="success" message={null} />)

  expect(container).toBeEmptyDOMElement()
})
