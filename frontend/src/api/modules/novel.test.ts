import { vi } from 'vitest'

const { getMock, postMock, putMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  putMock: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  apiClient: { get: getMock, post: postMock, put: putMock },
  getConfiguredAccessToken: () => 'test-token',
}))

import {
  listNovelBooks,
  saveNovelProgress,
  searchNovelBooks,
  sendNovelMessage,
  parseNovelSse,
} from './novel'

test('novel module uses the canonical bookshelf and reading-search endpoints', async () => {
  getMock
    .mockResolvedValueOnce({ success: true, code: 'OK', message: 'ok', data: [], meta: {}, trace_id: null })
  postMock.mockResolvedValueOnce({ success: true, code: 'OK', message: 'ok', data: [], meta: {}, trace_id: null })

  await listNovelBooks()
  await searchNovelBooks('远方')

  expect(getMock).toHaveBeenNthCalledWith(1, '/novel/books')
  expect(postMock).toHaveBeenCalledWith('/reading/search', { keyword: '远方', limit_per_source: 5 })
})

test('novel module sends scoped reader progress and assistant context', async () => {
  putMock.mockResolvedValueOnce({ success: true, code: 'OK', message: 'saved', data: {}, meta: {}, trace_id: null })
  postMock.mockResolvedValueOnce({ success: true, code: 'OK', message: 'ok', data: {}, meta: {}, trace_id: null })

  await saveNovelProgress(7, { chapterId: 2, offsetChars: 14, percent: 0.4, preferences: { theme: 'night' } })
  await sendNovelMessage('conversation-1', {
    content: '继续分析',
    entrypoint: 'reader',
    bookId: 7,
    chapterId: 2,
    mode: 'chat',
    stream: false,
  })

  expect(putMock).toHaveBeenCalledWith('/novel/books/7/progress', {
    chapter_id: 2,
    offset_chars: 14,
    percent: 0.4,
    preferences: { theme: 'night' },
  })
  expect(postMock).toHaveBeenCalledWith('/novel/conversations/conversation-1/messages', expect.objectContaining({
    content: '继续分析',
    entrypoint: 'reader',
    book_id: 7,
    chapter_id: 2,
    stream: false,
  }))
})

test('novel SSE parser ignores undocumented events and preserves text deltas', () => {
  expect(parseNovelSse([
    'event: started',
    'data: {}',
    '',
    'event: delta',
    'data: {"text":"第一段"}',
    '',
    'event: debug',
    'data: {"secret":"hidden"}',
    '',
    'event: completed',
    'data: {}',
    '',
  ].join('\n'))).toEqual([
    { event: 'started', data: {} },
    { event: 'delta', data: { text: '第一段' } },
    { event: 'completed', data: {} },
  ])
})
