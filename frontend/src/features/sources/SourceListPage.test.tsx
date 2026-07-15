import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, vi } from 'vitest'

class DeferredFileReader {
  static instances: DeferredFileReader[] = []

  result: string | ArrayBuffer | null = null
  error: DOMException | null = null
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null

  readAsText() {
    DeferredFileReader.instances.push(this)
  }

  abort() {
    this.onabort?.()
  }

  finish(text: string) {
    this.result = text
    this.onload?.()
  }
}

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
  DeferredFileReader.instances = []
})

afterEach(() => {
  vi.unstubAllGlobals()
})

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
  expect(screen.getByRole('link', { name: '编辑规则' })).toHaveAttribute('href', '/sources/rules/version-1')
})

test('source list imports a selected Legado JSON file as candidate sources', async () => {
  const { importLegadoSources } = await import('@/api/modules/sources')
  const file = new File([
    JSON.stringify([{ bookSourceName: '文件书源', bookSourceUrl: 'https://file.example.test' }]),
  ], 'legado-sources.json', { type: 'application/json' })
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  fireEvent.change(await screen.findByLabelText('选择 Legado JSON 文件'), {
    target: { files: [file] },
  })

  await waitFor(() => {
    expect(importLegadoSources).toHaveBeenCalledWith([
      { bookSourceName: '文件书源', bookSourceUrl: 'https://file.example.test' },
    ])
  })
  expect(await screen.findByText('已创建 1 个候选书源')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '编辑规则' })).toHaveAttribute('href', '/sources/rules/version-1')
  expect(screen.getByLabelText('Legado JSON')).toHaveValue('')
})

test('source list rejects malformed or scalar JSON files without importing', async () => {
  const { importLegadoSources } = await import('@/api/modules/sources')
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  fireEvent.change(await screen.findByLabelText('选择 Legado JSON 文件'), {
    target: { files: [new File(['{not-json'], 'broken.json', { type: 'application/json' })] },
  })

  expect(await screen.findByText('JSON 格式错误，请检查括号、逗号和引号。')).toBeInTheDocument()
  expect(importLegadoSources).not.toHaveBeenCalled()

  fireEvent.change(screen.getByLabelText('选择 Legado JSON 文件'), {
    target: { files: [new File(['"not a source"'], 'scalar.json', { type: 'application/json' })] },
  })

  expect(await screen.findByText('导入内容必须是一个书源对象或书源数组。')).toBeInTheDocument()
  expect(importLegadoSources).not.toHaveBeenCalled()
})

test('source list ignores a pending file read after unmounting', async () => {
  const { importLegadoSources } = await import('@/api/modules/sources')
  vi.stubGlobal('FileReader', DeferredFileReader as unknown as typeof FileReader)
  const { unmount } = render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  fireEvent.change(await screen.findByLabelText('选择 Legado JSON 文件'), {
    target: { files: [new File(['unused'], 'pending.json', { type: 'application/json' })] },
  })
  await waitFor(() => expect(DeferredFileReader.instances).toHaveLength(1))

  unmount()
  DeferredFileReader.instances[0].finish('[{"bookSourceName":"迟到书源","bookSourceUrl":"https://late.example.test"}]')

  await Promise.resolve()
  expect(importLegadoSources).not.toHaveBeenCalled()
})

test('source list blocks paste submission during a file read and ignores a stale file completion', async () => {
  const { importLegadoSources } = await import('@/api/modules/sources')
  vi.stubGlobal('FileReader', DeferredFileReader as unknown as typeof FileReader)
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)

  const fileInput = await screen.findByLabelText('选择 Legado JSON 文件')
  const importButton = screen.getByRole('button', { name: '导入书源' })
  fireEvent.change(fileInput, {
    target: { files: [new File(['first'], 'first.json', { type: 'application/json' })] },
  })
  await waitFor(() => expect(DeferredFileReader.instances).toHaveLength(1))
  expect(fileInput).toBeDisabled()
  expect(importButton).toBeDisabled()

  fireEvent.change(screen.getByLabelText('Legado JSON'), {
    target: { value: '[{"bookSourceName":"粘贴书源","bookSourceUrl":"https://paste.example.test"}]' },
  })
  fireEvent.submit(importButton.closest('form')!)
  expect(importLegadoSources).not.toHaveBeenCalled()

  fireEvent.change(fileInput, {
    target: { files: [new File(['second'], 'second.json', { type: 'application/json' })] },
  })
  await waitFor(() => expect(DeferredFileReader.instances).toHaveLength(2))

  DeferredFileReader.instances[0].finish('[{"bookSourceName":"过期书源","bookSourceUrl":"https://stale.example.test"}]')
  await Promise.resolve()
  expect(importLegadoSources).not.toHaveBeenCalled()

  DeferredFileReader.instances[1].finish('[{"bookSourceName":"当前书源","bookSourceUrl":"https://current.example.test"}]')
  await waitFor(() => {
    expect(importLegadoSources).toHaveBeenCalledWith([
      { bookSourceName: '当前书源', bookSourceUrl: 'https://current.example.test' },
    ])
  })
})
