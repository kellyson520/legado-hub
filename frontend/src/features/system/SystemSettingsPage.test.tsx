import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

const systemMocks = vi.hoisted(() => ({
  updateLLMSettings: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'saved',
    data: {
      providerName: 'Primary OpenAI',
      provider_name: 'Primary OpenAI',
      baseUrl: 'https://api.openai.com/v1',
      base_url: 'https://api.openai.com/v1',
      model: 'gpt-4.1-mini',
      apiKeyConfigured: true,
      api_key_configured: true,
    },
    meta: {},
    trace_id: null,
  }),
}))

vi.mock('@/api/modules/system', () => ({
  listProviders: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{ id: 'provider-1', name: 'Primary OpenAI', status: 'healthy' }],
    meta: { total: 1 },
    trace_id: null,
  }),
  listQuotaPolicies: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{ id: 'quota-1', scope: 'user:admin', dailyCostLimit: 50 }],
    meta: { total: 1 },
    trace_id: null,
  }),
  getLLMSettings: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      providerName: 'local-llm',
      provider_name: 'local-llm',
      baseUrl: '',
      base_url: '',
      model: 'gpt-4.1-mini',
      apiKeyConfigured: false,
      api_key_configured: false,
    },
    meta: {},
    trace_id: null,
  }),
  updateLLMSettings: systemMocks.updateLLMSettings,
}))

vi.mock('@/api/modules/ai', () => ({
  listAITasks: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        id: 'ai-1',
        name: 'Character analysis',
        status: 'succeeded',
        provider: 'Primary OpenAI',
        model: 'gpt-4.1-mini',
        cost: '$0.12',
      },
    ],
    meta: { total: 1 },
    trace_id: null,
  }),
}))

import { AITasksPage } from '@/features/ai/AITasksPage'
import { SystemSettingsPage } from './SystemSettingsPage'

test('system settings page shows provider health and quota panels', async () => {
  render(<SystemSettingsPage />)

  expect(await screen.findByText('Provider health')).toBeInTheDocument()
  expect(await screen.findByText('Quota policies')).toBeInTheDocument()
})

test('system settings page saves llm api configuration', async () => {
  render(<SystemSettingsPage />)

  expect(await screen.findByText('LLM API configuration')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Provider name'), {
    target: { value: 'Primary OpenAI' },
  })
  fireEvent.change(screen.getByLabelText('Base URL'), {
    target: { value: 'https://api.openai.com/v1' },
  })
  fireEvent.change(screen.getByLabelText('API Key'), {
    target: { value: 'sk-test' },
  })
  fireEvent.change(screen.getByLabelText('Model'), {
    target: { value: 'gpt-4.1-mini' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save LLM settings' }))

  await waitFor(() => {
    expect(systemMocks.updateLLMSettings).toHaveBeenCalledWith({
      providerName: 'Primary OpenAI',
      baseUrl: 'https://api.openai.com/v1',
      apiKey: 'sk-test',
      model: 'gpt-4.1-mini',
    })
  })
  expect(await screen.findByText('LLM settings saved')).toBeInTheDocument()
})

test('ai tasks page shows provider and model for each task', async () => {
  render(<AITasksPage />)

  expect(await screen.findByText('provider')).toBeInTheDocument()
  expect(await screen.findByText('model')).toBeInTheDocument()
})
