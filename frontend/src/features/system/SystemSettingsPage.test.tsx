import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, vi } from 'vitest'

const systemMocks = vi.hoisted(() => ({
  getSourceBuildAgentSettings: vi.fn(),
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
  updateSourceBuildAgentSettings: vi.fn(),
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
  getSourceBuildAgentSettings: systemMocks.getSourceBuildAgentSettings,
  updateLLMSettings: systemMocks.updateLLMSettings,
  updateSourceBuildAgentSettings: systemMocks.updateSourceBuildAgentSettings,
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

const sourceBuildAgentSettings = {
  success: true,
  code: 'OK',
  message: 'ok',
  data: {
    enabled: false,
    provider_configured: false,
  },
  meta: {},
  trace_id: null,
}

beforeEach(() => {
  systemMocks.getSourceBuildAgentSettings.mockReset().mockResolvedValue(sourceBuildAgentSettings)
  systemMocks.updateSourceBuildAgentSettings.mockReset().mockResolvedValue({
    ...sourceBuildAgentSettings,
    data: {
      enabled: true,
      provider_configured: false,
    },
  })
})

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

test('system settings page defaults source build Agent off and persists an enabled setting', async () => {
  render(<SystemSettingsPage />)

  const sourceBuildAgentSwitch = await screen.findByRole('switch', { name: 'Agent-enhanced source build' })
  expect(sourceBuildAgentSwitch).not.toBeChecked()
  expect(
    screen.getByText('仅当确定性书源构建失败后才会调用 Agent / Agent runs only after deterministic source build fails.'),
  ).toBeInTheDocument()
  expect(screen.getByText('LLM provider 未配置 / Provider not configured')).toBeInTheDocument()

  fireEvent.click(sourceBuildAgentSwitch)

  await waitFor(() => {
    expect(systemMocks.updateSourceBuildAgentSettings).toHaveBeenCalledWith({ enabled: true })
  })
  expect(sourceBuildAgentSwitch).toBeChecked()
})

test('system settings page disables the source build Agent switch while saving', async () => {
  let resolveUpdate: (value: typeof sourceBuildAgentSettings) => void
  systemMocks.updateSourceBuildAgentSettings.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveUpdate = resolve
      }),
  )
  render(<SystemSettingsPage />)

  const sourceBuildAgentSwitch = await screen.findByRole('switch', { name: 'Agent-enhanced source build' })
  fireEvent.click(sourceBuildAgentSwitch)

  expect(sourceBuildAgentSwitch).toBeDisabled()

  resolveUpdate!({
    ...sourceBuildAgentSettings,
    data: {
      enabled: true,
      provider_configured: false,
    },
  })
  await waitFor(() => expect(sourceBuildAgentSwitch).not.toBeDisabled())
})

test('system settings page supports camelCase Agent provider configuration', async () => {
  systemMocks.getSourceBuildAgentSettings.mockResolvedValueOnce({
    ...sourceBuildAgentSettings,
    data: {
      enabled: true,
      providerConfigured: true,
    },
  })
  render(<SystemSettingsPage />)

  expect(await screen.findByRole('switch', { name: 'Agent-enhanced source build' })).toBeChecked()
  expect(screen.getByText('LLM provider 已配置 / Provider configured')).toBeInTheDocument()
})

test('system settings page keeps LLM panels available when Agent settings fail to load', async () => {
  systemMocks.getSourceBuildAgentSettings.mockRejectedValueOnce(new Error('settings unavailable'))
  render(<SystemSettingsPage />)

  expect(await screen.findByText('LLM API configuration')).toBeInTheDocument()
  expect(await screen.findByText('Provider health')).toBeInTheDocument()
  expect(await screen.findByText('Quota policies')).toBeInTheDocument()
  expect(await screen.findByText('Primary OpenAI · healthy')).toBeInTheDocument()
  expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load source build Agent settings')
})

test('system settings page prevents toggling Agent settings before the initial load completes', async () => {
  let resolveInitialSettings: (value: typeof sourceBuildAgentSettings) => void
  systemMocks.getSourceBuildAgentSettings.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveInitialSettings = resolve
      }),
  )
  render(<SystemSettingsPage />)

  const sourceBuildAgentSwitch = await screen.findByRole('switch', { name: 'Agent-enhanced source build' })
  expect(sourceBuildAgentSwitch).toBeDisabled()
  expect(systemMocks.updateSourceBuildAgentSettings).not.toHaveBeenCalled()

  resolveInitialSettings!(sourceBuildAgentSettings)
  await waitFor(() => expect(sourceBuildAgentSwitch).not.toBeDisabled())
})

test('system settings page announces Agent settings save failures as errors', async () => {
  systemMocks.updateSourceBuildAgentSettings.mockRejectedValueOnce(new Error('save unavailable'))
  render(<SystemSettingsPage />)

  const sourceBuildAgentSwitch = await screen.findByRole('switch', { name: 'Agent-enhanced source build' })
  fireEvent.click(sourceBuildAgentSwitch)

  expect(await screen.findByRole('alert')).toHaveTextContent('Failed to save source build Agent settings')
})

test('ai tasks page shows provider and model for each task', async () => {
  render(<AITasksPage />)

  expect(await screen.findByText('provider')).toBeInTheDocument()
  expect(await screen.findByText('model')).toBeInTheDocument()
})
