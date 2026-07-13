import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'

vi.mock('@/api/modules/sources', () => ({
  getSourceVersion: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      source_version_id: 'source-version-1',
      source_type: 'book',
      source_id: 'https://example.test',
      status: 'candidate',
      payload: {
        bookSourceName: '示例书源',
        bookSourceUrl: 'https://example.test',
        ruleSearch: { url: '/search?key={{key}}' },
        ruleToc: { chapterList: '.chapter-item' },
        ruleContent: { content: '#content' },
      },
      content_status: 'ready',
      publish_allowed: false,
      latest_validation: null,
    },
    meta: {},
    trace_id: null,
  }),
  createSourceDraft: vi.fn(),
  validateSourceVersion: vi.fn(),
  publishSourceVersion: vi.fn(),
}))

vi.mock('@/api/modules/engine', () => ({
  testEngineRegex: vi.fn(),
}))

vi.mock('@/app/providers/AuthProvider', () => ({
  useAuth: () => ({ hasPermission: () => true }),
}))

import { SourceRuleEditorPage } from './SourceRuleEditorPage'

test('规则 JSON 非法时禁止保存候选版本', async () => {
  render(
    <MemoryRouter initialEntries={['/sources/rules/source-version-1']}>
      <Routes>
        <Route path="/sources/rules/:sourceVersionId" element={<SourceRuleEditorPage />} />
      </Routes>
    </MemoryRouter>
  )

  expect(await screen.findByDisplayValue('示例书源')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '保存候选' })).toBeEnabled()

  fireEvent.change(screen.getByLabelText('规则 JSON'), { target: { value: '{"ruleSearch":' } })

  expect(screen.getByText('规则 JSON 格式错误，修正后才能保存候选版本。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '保存候选' })).toBeDisabled()
})
