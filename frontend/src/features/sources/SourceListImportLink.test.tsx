import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

vi.mock('@/api/modules/sources', () => ({
  listBookSources: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [],
    meta: { page: 1, total: 0 },
    trace_id: null,
  }),
  importLegadoSources: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      items: [
        {
          index: 0,
          status: 'created',
          source_url: 'https://example.test',
          source_version_id: 'source-version-1',
        },
      ],
    },
    meta: {},
    trace_id: null,
  }),
  exportLegadoSources: vi.fn(),
}))

import { SourceListPage } from './SourceListPage'

test('source import exposes a direct link to edit each created candidate rule', async () => {
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  fireEvent.change(await screen.findByLabelText('Legado JSON'), {
    target: { value: '[{"bookSourceName":"示例书源","bookSourceUrl":"https://example.test"}]' },
  })
  fireEvent.click(screen.getByRole('button', { name: '导入书源' }))

  expect(await screen.findByRole('link', { name: '编辑规则' })).toHaveAttribute(
    'href',
    '/sources/rules/source-version-1'
  )
})
