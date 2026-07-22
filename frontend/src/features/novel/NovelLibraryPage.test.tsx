import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

const novelMocks = vi.hoisted(() => ({
  listNovelBooks: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{
      id: 7,
      book_name: '测试书',
      author: '作者',
      source_name: '用户上传',
      status: 'summarizing',
      total_chapters: 10,
      total_words: 12000,
      ingest_progress: 0.8,
      progress: { chapter_id: 4, chapter_title: '第四章', percent: 0.42, offset_chars: 120 },
      updated_at: '2026-07-21T08:00:00Z',
    }],
    meta: { total: 1 },
    trace_id: null,
  }),
  searchNovelBooks: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{ bookUrl: 'https://source.test/book', name: '远方', author: '作者', sourceId: 3, sourceName: '示例源' }],
    meta: { total: 1 },
    trace_id: null,
  }),
  importNovelFromSource: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'queued',
    data: { book_id: 8, status: 'queued', task_id: 'task-8' },
    meta: {},
    trace_id: null,
  }),
  uploadNovel: vi.fn(),
  createNovelConversation: vi.fn(),
}))

vi.mock('@/api/modules/novel', () => novelMocks)

import { NovelLibraryPage } from './NovelLibraryPage'

test('书架显示进度并能从书源搜索结果加入书架', async () => {
  render(<MemoryRouter><NovelLibraryPage /></MemoryRouter>)

  expect(await screen.findByText('42%')).toBeInTheDocument()
  expect(screen.getByText(/第四章/)).toBeInTheDocument()

  fireEvent.change(screen.getByLabelText('搜索书名'), { target: { value: '远方' } })
  fireEvent.click(screen.getByRole('button', { name: '搜书' }))

  expect(await screen.findByRole('button', { name: '加入书架' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '加入书架' }))

  await waitFor(() => {
    expect(novelMocks.importNovelFromSource).toHaveBeenCalledWith({
      sourceId: 3,
      bookUrl: 'https://source.test/book',
      name: '远方',
      author: '作者',
    })
  })
})

test('书架上传小说时把文件交给统一导入接口', async () => {
  novelMocks.uploadNovel.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'queued',
    data: { book_id: 9, status: 'queued', task_id: 'task-9' },
    meta: {},
    trace_id: null,
  })
  render(<MemoryRouter><NovelLibraryPage /></MemoryRouter>)

  const file = new File(['第一章\n内容'], '测试书.txt', { type: 'text/plain' })
  fireEvent.change(screen.getByLabelText('上传小说'), { target: { files: [file] } })

  await waitFor(() => expect(novelMocks.uploadNovel).toHaveBeenCalledWith(file))
  expect(await screen.findByText(/导入任务已创建/)).toBeInTheDocument()
})

test('书架把分析失败显示为明确的终态', async () => {
  novelMocks.listNovelBooks.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{
      id: 7,
      book_name: '失败书',
      status: 'error',
      ingest_error_msg: 'provider unavailable',
      total_chapters: 1,
      ingest_progress: 0.3,
    }],
    meta: { total: 1 },
    trace_id: null,
  })

  render(<MemoryRouter><NovelLibraryPage /></MemoryRouter>)

  expect(await screen.findByText('分析失败，可重试')).toBeInTheDocument()
})
