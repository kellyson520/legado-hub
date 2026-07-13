import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  importLegadoSources: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: { items: [{ index: 0, status: 'created', source_url: 'https://example.test' }] },
    meta: {},
    trace_id: null,
  }),
  exportLegadoSources: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [],
    meta: { total: 0 },
    trace_id: null,
  }),
}))

import { SourceListPage } from './SourceListPage'

test('source list renders current status, published version, and latest run grade', async () => {
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  expect(await screen.findByText('Published')).toBeInTheDocument()
  expect(await screen.findByText('最近评分')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '书源运行库存' })).toBeVisible()
  expect(screen.getByRole('link', { name: '打开书源健康控制台' })).toHaveClass('inline-flex')
})

test('source list imports Legado JSON as candidate sources', async () => {
  const { importLegadoSources } = await import('@/api/modules/sources')
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  fireEvent.change(await screen.findByLabelText('Legado JSON'), {
    target: { value: '[{"bookSourceName":"示例源","bookSourceUrl":"https://example.test"}]' },
  })
  fireEvent.click(screen.getByRole('button', { name: '导入书源' }))

  await waitFor(() => {
    expect(importLegadoSources).toHaveBeenCalledWith([
      { bookSourceName: '示例源', bookSourceUrl: 'https://example.test' },
    ])
  })
  expect(await screen.findByText('已创建 1 个候选书源')).toBeInTheDocument()
})
