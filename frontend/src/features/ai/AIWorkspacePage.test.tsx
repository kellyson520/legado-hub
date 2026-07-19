import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

const aiMocks = vi.hoisted(() => ({
  listAIConversations: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{ id: 'conversation-1', title: '书源助手', created_at: '2026-07-13T00:00:00Z' }],
    meta: { total: 1 },
    trace_id: null,
  }),
  createAIConversation: vi.fn(),
  getAIConversation: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      id: 'conversation-1',
      title: '书源助手',
      created_at: '2026-07-13T00:00:00Z',
      messages: [{
        id: 'message-1',
        role: 'assistant',
        mode: 'character',
        content: '主角是一个谨慎的探索者。',
        status: 'succeeded',
        created_at: '2026-07-13T00:00:01Z',
        tool_calls: [{
          name: 'list_visible_sources',
          arguments: {},
          result: [{ id: 'source-1', name: '示例书源', status: 'published' }],
        }],
      }],
    },
    meta: {},
    trace_id: null,
  }),
  sendAIConversationMessage: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      id: 'message-2',
      role: 'assistant',
      mode: 'character',
      content: '主角在冲突中选择保护同伴。',
      status: 'succeeded',
      created_at: '2026-07-13T00:01:00Z',
      tool_calls: [],
    },
    meta: {},
    trace_id: null,
  }),
  decideAIConversationAuthorization: vi.fn(),
  listAIConversationAuthorizations: vi.fn().mockResolvedValue({ success: true, code: 'OK', message: 'ok', data: [], meta: {}, trace_id: null }),
  listAIAuthorizationGrants: vi.fn().mockResolvedValue({ success: true, code: 'OK', message: 'ok', data: [], meta: {}, trace_id: null }),
  revokeAIAuthorizationGrant: vi.fn(),
}))

const statusMocks = vi.hoisted(() => ({
  ListStatus: vi.fn((props: { loading: boolean; empty: boolean }) => {
    void props
    return null
  }),
}))

vi.mock('@/api/modules/ai', () => aiMocks)
vi.mock('@/components/data/ListStatus', () => statusMocks)

import { AIWorkspacePage } from './AIWorkspacePage'

test('工作台按中文模式发送消息并显示工具引用', async () => {
  render(<AIWorkspacePage />)

  expect((await screen.findAllByText('书源助手')).length).toBeGreaterThan(0)
  expect(await screen.findByText('引用的工具结果')).toBeInTheDocument()
  expect(statusMocks.ListStatus.mock.calls.some(([props]) => props.loading === false && props.empty === false)).toBe(true)

  fireEvent.click(screen.getByRole('button', { name: '人物介绍' }))
  fireEvent.change(screen.getByLabelText('输入消息'), { target: { value: '介绍主角' } })
  fireEvent.click(screen.getByRole('button', { name: '发送' }))

  await waitFor(() => {
    expect(aiMocks.sendAIConversationMessage).toHaveBeenCalledWith('conversation-1', expect.objectContaining({
      mode: 'character',
      content: '介绍主角',
    }))
  })
  expect(await screen.findByText('主角在冲突中选择保护同伴。')).toBeInTheDocument()
})

test('失败消息显示安全提示并允许重试', async () => {
  aiMocks.getAIConversation.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      id: 'conversation-1',
      title: '书源助手',
      created_at: '2026-07-13T00:00:00Z',
      messages: [{
        id: 'failed-1',
        role: 'assistant',
        mode: 'chat',
        content: '服务调用失败，请稍后重试。',
        status: 'failed',
        created_at: '2026-07-13T00:00:01Z',
        tool_calls: [],
      }],
    },
    meta: {},
    trace_id: null,
  })

  render(<AIWorkspacePage />)

  expect(await screen.findByText('服务调用失败，请稍后重试。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
})

test('正文读取前显示授权卡片并在本次允许后追加恢复结果', async () => {
  aiMocks.getAIConversation.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      id: 'conversation-1',
      title: '书源助手',
      created_at: '2026-07-13T00:00:00Z',
      messages: [{
        id: 'authorization-message-1',
        role: 'assistant',
        mode: 'character',
        content: '需要你的授权才能读取书源原文。',
        status: 'authorization_required',
        created_at: '2026-07-13T00:00:01Z',
        tool_calls: [],
        authorization_request: {
          id: 'request-1',
          tools: ['source.search', 'toc.get', 'chapter.fetch'],
          purpose: '读取书源原文以便基于证据分析人物',
          status: 'pending',
          choices: ['once', 'conversation', 'remember', 'deny'],
          expires_at: '2099-01-01T00:00:00Z',
        },
      }],
    },
    meta: {},
    trace_id: null,
  })
  aiMocks.decideAIConversationAuthorization.mockResolvedValueOnce({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      authorization: { id: 'request-1', status: 'consumed', decision: 'once' },
      message: {
        id: 'resumed-message-1',
        role: 'assistant',
        mode: 'character',
        content: '已基于书源原文继续分析。',
        status: 'succeeded',
        created_at: '2026-07-13T00:00:02Z',
        tool_calls: [],
      },
    },
    meta: {},
    trace_id: null,
  })

  render(<AIWorkspacePage />)

  expect(await screen.findByText('读取书源原文以便基于证据分析人物')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '本次允许' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '本次允许' }))

  await waitFor(() => {
    expect(aiMocks.decideAIConversationAuthorization).toHaveBeenCalledWith(
      'conversation-1', 'request-1', { decision: 'once' },
    )
  })
  expect(await screen.findByText('已基于书源原文继续分析。')).toBeInTheDocument()
})
