import { vi } from 'vitest'

const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  apiClient: {
    get: getMock,
  },
}))

import { listAITasks } from '@/api/modules/ai'
import { listTranslationJobs } from '@/api/modules/translation'

test('ai module normalizes backend task rows for the console', async () => {
  getMock.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 'ai-1',
        name: 'Demo',
        status: 'succeeded',
        provider: 'local-llm',
        model: 'gpt-4.1-mini',
        cost: 0.12,
      },
    ],
    meta: { total: 1 },
    trace_id: null,
  })

  const response = await listAITasks()

  expect(response.data[0].cost).toBe('$0.12')
})

test('translation module maps snake_case backend fields to console rows', async () => {
  getMock.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 'tr-1',
        source_language: 'zh',
        target_language: 'en',
        status: 'succeeded',
        provider: 'local-llm',
        progress: '100%',
      },
    ],
    meta: { total: 1 },
    trace_id: null,
  })

  const response = await listTranslationJobs()

  expect(response.data[0].targetLanguage).toBe('en')
  expect(response.data[0].name).toBe('zh→en')
})
