import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

vi.mock('@/api/modules/sources', () => ({
  listBookSources: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 'source-1',
        name: 'Published',
        status: 'published',
        publishedVersion: 'v3',
        latestGrade: 'A',
      },
    ],
    meta: { page: 1, total: 1 },
    trace_id: null,
  }),
}))

import { SourceListPage } from './SourceListPage'

test('source list renders current status, published version, and latest run grade', async () => {
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  expect(await screen.findByText('Published')).toBeInTheDocument()
  expect(await screen.findByText('Latest grade')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Runtime source inventory' })).toBeVisible()
  expect(screen.getByRole('link', { name: 'Open source health control plane' })).toHaveClass('inline-flex')
})
