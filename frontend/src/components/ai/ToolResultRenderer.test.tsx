import { render, screen } from '@testing-library/react'

import { ToolResultRenderer } from './ToolResultRenderer'

test('工具数组结果优先渲染为可读表格', () => {
  render(<ToolResultRenderer value={[{ name: '江轩', confidence: 0.92 }, { name: '周宁', confidence: 0.81 }]} />)

  expect(screen.getByRole('table')).toBeInTheDocument()
  expect(screen.getByText('name')).toBeInTheDocument()
  expect(screen.getByText('江轩')).toBeInTheDocument()
  expect(screen.getByText('0.92')).toBeInTheDocument()
})

test('工具对象结果渲染为键值列表，保留嵌套内容但限制文本长度', () => {
  render(<ToolResultRenderer value={{ status: 'completed', evidence: [{ chapter_num: 1, text: '序章证据' }] }} />)

  expect(screen.getByText('status')).toBeInTheDocument()
  expect(screen.getByText('completed')).toBeInTheDocument()
  expect(screen.getByText(/序章证据/)).toBeInTheDocument()
})

test('工具返回 Markdown 字符串时渲染为富文本表格', () => {
  render(<ToolResultRenderer value={'| 人物 | 身份 |\n| --- | --- |\n| 陈舟 | 主角 |'} />)

  expect(screen.getByRole('table')).toBeInTheDocument()
  expect(screen.getByRole('columnheader', { name: '人物' })).toBeInTheDocument()
  expect(screen.getByText('陈舟')).toBeInTheDocument()
  expect(screen.queryByText('| 人物 | 身份 |')).not.toBeInTheDocument()
})
