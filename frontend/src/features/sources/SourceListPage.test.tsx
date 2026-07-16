import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, vi } from 'vitest'

vi.mock('@/api/modules/sources', () => ({
  listBookSources: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 1,
        bookSourceName: '运行书源',
        bookSourceUrl: 'https://source.example.test',
        bookSourceGroup: '测试',
        enabled: true,
        sourceStatus: 'enabled',
        sourceOrigin: 'imported',
        lastCheckTime: '2026-07-15T10:00:00Z',
        errorMsg: '',
        payload: {},
      },
    ],
    meta: { page: 1, total: 1 },
    trace_id: null,
  }),
  importLegadoSources: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      items: [{
        index: 0,
        status: 'created',
        source_url: 'https://example.test',
        source_version_id: 'version-1',
      }],
    },
    meta: {},
    trace_id: null,
  }),
  importLegadoSourceFile: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      items: [{ index: 0, status: 'created', source_url: 'https://file.example.test', source_version_id: 'version-file-1' }],
    },
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

beforeEach(() => {
  vi.clearAllMocks()
})

test('source list renders legacy runtime name, URL, and source status', async () => {
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  expect(await screen.findByText('运行书源')).toBeInTheDocument()
  expect(screen.getByText('https://source.example.test')).toBeInTheDocument()
  expect(screen.getByText('enabled')).toBeInTheDocument()
  expect(screen.queryByText('已发布版本')).not.toBeInTheDocument()
  expect(screen.queryByText('最近评分')).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '书源运行库存' })).toBeVisible()
  expect(screen.getByRole('link', { name: '打开书源健康控制台' })).toHaveClass('inline-flex')
})

test('source list keeps a review link for persisted candidate versions', async () => {
  const { listBookSources } = await import('@/api/modules/sources')
  vi.mocked(listBookSources).mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{
      id: 'candidate-version-1',
      bookSourceName: '待审核书源',
      bookSourceUrl: 'https://candidate.example.test',
      bookSourceGroup: '测试',
      enabled: true,
      sourceStatus: 'candidate',
      sourceOrigin: 'runtime_version',
      lastCheckTime: '2026-07-16T10:00:00Z',
      errorMsg: null,
      payload: {},
    }],
    meta: { page: 1, total: 1 },
    trace_id: null,
  })

  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  expect(await screen.findByRole('link', { name: '审核规则' })).toHaveAttribute(
    'href',
    '/sources/rules/candidate-version-1'
  )
})

test('source list loads further pages when the visible inventory exceeds the initial page', async () => {
  const { listBookSources } = await import('@/api/modules/sources')
  vi.mocked(listBookSources)
    .mockResolvedValueOnce({
      success: true,
      code: 'OK',
      message: 'ok',
      data: [{
        id: 'candidate-version-1',
        bookSourceName: '第一个候选书源',
        bookSourceUrl: 'https://first.example.test',
        bookSourceGroup: '测试',
        enabled: true,
        sourceStatus: 'candidate',
        sourceOrigin: 'runtime_version',
        lastCheckTime: '2026-07-16T10:00:00Z',
        errorMsg: null,
        payload: {},
      }],
      meta: { page: 1, page_size: 100, total: 2 },
      trace_id: null,
    })

  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  expect(await screen.findByText('第一个候选书源')).toBeInTheDocument()
  expect(screen.getByText('已显示 1 / 2 个书源')).toBeInTheDocument()
  vi.mocked(listBookSources).mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{
      id: 'candidate-version-2',
      bookSourceName: '第二个候选书源',
      bookSourceUrl: 'https://second.example.test',
      bookSourceGroup: '测试',
      enabled: true,
      sourceStatus: 'candidate',
      sourceOrigin: 'runtime_version',
      lastCheckTime: '2026-07-16T10:00:00Z',
      errorMsg: null,
      payload: {},
    }],
    meta: { page: 2, page_size: 100, total: 2 },
    trace_id: null,
  })
  fireEvent.click(screen.getByRole('button', { name: '加载更多书源' }))

  await waitFor(() => {
    expect(listBookSources).toHaveBeenLastCalledWith({ page: 2, page_size: 100 })
  })
  expect(await screen.findByText('第二个候选书源')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '加载更多书源' })).not.toBeInTheDocument()
})

test('source list stops loading and explains when the runtime inventory cannot be loaded', async () => {
  const { listBookSources } = await import('@/api/modules/sources')
  vi.mocked(listBookSources).mockRejectedValueOnce(new Error('network unavailable'))
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  expect(await screen.findByRole('alert')).toHaveTextContent('无法加载书源库存，请重试。')
  expect(screen.queryByText('正在加载书源…')).not.toBeInTheDocument()
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
  expect(screen.getByRole('link', { name: '编辑规则' })).toHaveAttribute('href', '/sources/rules/version-1')
})

test('source list exposes an upload button that opens the Legado JSON file picker', async () => {
  const click = vi.spyOn(HTMLInputElement.prototype, 'click')
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  await screen.findByText('运行书源')
  fireEvent.click(screen.getByRole('button', { name: '上传 JSON 文件' }))

  expect(click).toHaveBeenCalled()
})

test('source list imports a selected Legado JSON file as candidate sources', async () => {
  const { importLegadoSourceFile } = await import('@/api/modules/sources')
  const file = new File([
    JSON.stringify([{ bookSourceName: '文件书源', bookSourceUrl: 'https://file.example.test' }]),
  ], 'legado-sources.json', { type: 'application/json' })
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  fireEvent.change(await screen.findByLabelText('选择 Legado JSON 文件'), {
    target: { files: [file] },
  })

  await waitFor(() => {
    expect(importLegadoSourceFile).toHaveBeenCalledWith(file)
  })
  expect(await screen.findByText('已创建 1 个候选书源')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '编辑规则' })).toHaveAttribute('href', '/sources/rules/version-file-1')
  expect(screen.getByLabelText('Legado JSON')).toHaveValue('')
})

test('source list reports a server-side JSON file rejection without parsing the file in the browser', async () => {
  const { importLegadoSourceFile } = await import('@/api/modules/sources')
  vi.mocked(importLegadoSourceFile).mockRejectedValueOnce(new Error('malformed JSON'))
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  fireEvent.change(await screen.findByLabelText('选择 Legado JSON 文件'), {
    target: { files: [new File(['{not-json'], 'broken.json', { type: 'application/json' })] },
  })

  expect(await screen.findByText('文件导入失败，请确认 JSON 格式、文件大小和登录权限。')).toBeInTheDocument()
  expect(importLegadoSourceFile).toHaveBeenCalledTimes(1)
})

test('source list blocks paste submission while a file upload is in progress', async () => {
  const { importLegadoSources } = await import('@/api/modules/sources')
  const { importLegadoSourceFile } = await import('@/api/modules/sources')
  let resolveUpload: (() => void) | undefined
  vi.mocked(importLegadoSourceFile).mockImplementationOnce(() => new Promise((resolve) => {
    resolveUpload = () => resolve({ success: true, code: 'OK', message: 'ok', data: { items: [] }, meta: {}, trace_id: null })
  }))
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  const fileInput = await screen.findByLabelText('选择 Legado JSON 文件')
  const importButton = screen.getByRole('button', { name: '导入书源' })
  fireEvent.change(fileInput, {
    target: { files: [new File(['first'], 'first.json', { type: 'application/json' })] },
  })
  await waitFor(() => expect(importLegadoSourceFile).toHaveBeenCalledTimes(1))
  expect(fileInput).toBeDisabled()
  expect(importButton).toBeDisabled()

  fireEvent.change(screen.getByLabelText('Legado JSON'), {
    target: { value: '[{"bookSourceName":"粘贴书源","bookSourceUrl":"https://paste.example.test"}]' },
  })
  fireEvent.submit(importButton.closest('form')!)
  expect(importLegadoSources).not.toHaveBeenCalled()
  resolveUpload?.()
  await waitFor(() => expect(fileInput).not.toBeDisabled())
})
