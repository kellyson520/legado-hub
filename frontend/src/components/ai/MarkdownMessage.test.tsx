import { render, screen } from '@testing-library/react'

import { MarkdownMessage } from './MarkdownMessage'

test('Markdown 消息渲染 GFM 表格、引用和代码块，并移除危险 HTML', () => {
  render(
    <MarkdownMessage
      content={'| 人物 | 状态 |\n| --- | --- |\n| 江轩 | 观察 |\n\n> 证据来自序章。\n\n```json\n{"ok":true}\n```\n\n<script>alert("xss")</script>'}
    />,
  )

  expect(screen.getByRole('table')).toBeInTheDocument()
  expect(screen.getByRole('blockquote')).toHaveTextContent('证据来自序章。')
  expect(screen.getByText('{"ok":true}')).toBeInTheDocument()
  expect(screen.queryByText('alert("xss")')).not.toBeInTheDocument()
})

test('Markdown 消息只允许安全链接协议', () => {
  render(<MarkdownMessage content={'[安全](https://example.com) [危险](javascript:alert(1))'} />)

  expect(screen.getByRole('link', { name: '安全' })).toHaveAttribute('href', 'https://example.com')
  expect(screen.queryByRole('link', { name: '危险' })).not.toBeInTheDocument()
  expect(screen.getByText('危险')).toBeInTheDocument()
})

test('Markdown 消息把旧式的行首※标记转换为列表', () => {
  render(<MarkdownMessage content={'※ 林远\n※ 周宁'} />)

  expect(screen.getByRole('list')).toBeInTheDocument()
  expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('林远')
  expect(screen.queryByText('※ 林远')).not.toBeInTheDocument()
})

test('Markdown 消息保留代码块中的※字符', () => {
  render(<MarkdownMessage content={'```text\n※ 这是代码中的原文\n```'} />)

  expect(screen.getByText('※ 这是代码中的原文')).toBeInTheDocument()
  expect(screen.queryByRole('list')).not.toBeInTheDocument()
})
