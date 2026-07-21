import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'

const novelMocks = vi.hoisted(() => ({
  getNovelBook: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: { id: 7, book_name: '测试书', author: '作者', total_chapters: 10 },
    meta: {},
    trace_id: null,
  }),
  listNovelChapters: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      { id: 1, book_id: 7, canonical_full: 'C1', chapter_num: 1, chapter_title: '第一章' },
      { id: 2, book_id: 7, canonical_full: 'C2', chapter_num: 2, chapter_title: '第二章' },
    ],
    meta: { total: 2 },
    trace_id: null,
  }),
  getNovelChapter: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: { id: 2, book_id: 7, chapter_title: '第二章', raw_text: '林远推开旧门。\n风从走廊尽头吹来。', word_count: 19 },
    meta: {},
    trace_id: null,
  }),
  getNovelProgress: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: { book_id: 7, chapter_id: 2, offset_chars: 0, percent: 0.42, theme: 'paper', font_size: 18 },
    meta: {},
    trace_id: null,
  }),
  saveNovelProgress: vi.fn().mockResolvedValue({ success: true, code: 'OK', message: 'saved', data: {}, meta: {}, trace_id: null }),
  createNovelConversation: vi.fn().mockResolvedValue({ success: true, code: 'OK', message: 'created', data: { id: 'conversation-reader', title: '阅读助手', messages: [] }, meta: {}, trace_id: null }),
  sendNovelMessage: vi.fn(),
}))

vi.mock('@/api/modules/novel', () => novelMocks)

import { NovelReaderPage } from './NovelReaderPage'

function renderReader() {
  return render(
    <MemoryRouter initialEntries={['/novel/books/7/read/2']}>
      <Routes>
        <Route path="/novel/books/:bookId/read/:chapterId" element={<NovelReaderPage />} />
      </Routes>
    </MemoryRouter>
  )
}

test('阅读器显示当前章节并把阅读上下文传给助手', async () => {
  renderReader()

  expect(await screen.findByRole('heading', { name: '第二章' })).toBeInTheDocument()
  expect(screen.getByText('林远推开旧门。')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: '问助手' }))

  await waitFor(() => {
    expect(novelMocks.createNovelConversation).toHaveBeenCalledWith(expect.objectContaining({
      bookId: 7,
      entrypoint: 'reader',
      chapterId: 2,
    }))
  })
  expect(await screen.findByText('阅读助手')).toBeInTheDocument()
})

test('阅读器支持夜读主题和字号调整，并保存阅读偏好', async () => {
  renderReader()
  await screen.findByRole('heading', { name: '第二章' })

  fireEvent.click(screen.getByRole('button', { name: '夜读' }))
  fireEvent.click(screen.getByRole('button', { name: '增大字号' }))

  expect(screen.getByTestId('reader-surface')).toHaveAttribute('data-reader-theme', 'night')
  expect(screen.getByTestId('reader-content')).toHaveStyle({ fontSize: '19px' })

  await waitFor(() => {
    expect(novelMocks.saveNovelProgress).toHaveBeenCalledWith(7, expect.objectContaining({
      chapterId: 2,
      preferences: expect.objectContaining({ theme: 'night', fontSize: 19 }),
    }))
  })
})
