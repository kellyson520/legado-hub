import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { beforeEach, vi } from 'vitest'

const systemMocks = vi.hoisted(() => ({
  getSourceBuildAgentSettings: vi.fn(),
  getInteractiveBrowserSettings: vi.fn(),
  createProvider: vi.fn(),
  updateProvider: vi.fn(),
  discoverProviderModels: vi.fn(),
  getProviderRoute: vi.fn(),
  updateProviderRoute: vi.fn(),
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
  updateInteractiveBrowserSettings: vi.fn(),
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
  getInteractiveBrowserSettings: systemMocks.getInteractiveBrowserSettings,
  createProvider: systemMocks.createProvider,
  updateProvider: systemMocks.updateProvider,
  discoverProviderModels: systemMocks.discoverProviderModels,
  getProviderRoute: systemMocks.getProviderRoute,
  updateProviderRoute: systemMocks.updateProviderRoute,
  updateLLMSettings: systemMocks.updateLLMSettings,
  updateSourceBuildAgentSettings: systemMocks.updateSourceBuildAgentSettings,
  updateInteractiveBrowserSettings: systemMocks.updateInteractiveBrowserSettings,
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

const interactiveBrowserSettings = {
  success: true,
  code: 'OK',
  message: 'ok',
  data: {
    enabled: false,
    automaticEnabled: true,
    maxSessions: 1,
    sessionTimeoutSeconds: 300,
  },
  meta: {},
  trace_id: null,
}

function deferred<T>() {
  let resolve: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve: resolve! }
}

beforeEach(() => {
  systemMocks.getSourceBuildAgentSettings.mockReset().mockResolvedValue(sourceBuildAgentSettings)
  systemMocks.createProvider.mockReset()
  systemMocks.updateProvider.mockReset()
  systemMocks.discoverProviderModels.mockReset()
  systemMocks.getProviderRoute.mockReset().mockImplementation((group: string) => Promise.resolve({
    ...sourceBuildAgentSettings,
    data: { group, entries: [] },
  }))
  systemMocks.updateProviderRoute.mockReset()
  systemMocks.updateSourceBuildAgentSettings.mockReset().mockResolvedValue({
    ...sourceBuildAgentSettings,
    data: {
      enabled: true,
      provider_configured: false,
    },
  })
  systemMocks.getInteractiveBrowserSettings.mockReset().mockResolvedValue(interactiveBrowserSettings)
  systemMocks.updateInteractiveBrowserSettings.mockReset().mockResolvedValue({
    ...interactiveBrowserSettings,
    data: {
      enabled: true,
      automaticEnabled: true,
      maxSessions: 3,
      sessionTimeoutSeconds: 60,
    },
  })
})

test('system settings page shows provider health and quota panels', async () => {
  render(<SystemSettingsPage />)

  expect(await screen.findByText('Provider 健康状态')).toBeInTheDocument()
  expect(await screen.findByText('配额策略')).toBeInTheDocument()
})

test('system settings page saves llm api configuration', async () => {
  systemMocks.getSourceBuildAgentSettings
    .mockResolvedValueOnce(sourceBuildAgentSettings)
    .mockResolvedValueOnce({
      ...sourceBuildAgentSettings,
      data: { enabled: false, provider_configured: true },
    })
    .mockResolvedValueOnce({
      ...sourceBuildAgentSettings,
      data: { enabled: false, provider_configured: true },
    })
  render(<SystemSettingsPage />)

  expect(await screen.findByText('LLM API 配置')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Provider 名称'), {
    target: { value: 'Primary OpenAI' },
  })
  fireEvent.change(screen.getByLabelText('基础 URL'), {
    target: { value: 'https://api.openai.com/v1' },
  })
  fireEvent.change(screen.getByLabelText('API Key'), {
    target: { value: 'sk-test' },
  })
  fireEvent.change(screen.getByLabelText('模型'), {
    target: { value: 'gpt-4.1-mini' },
  })
  fireEvent.click(screen.getByRole('button', { name: '保存 LLM 设置' }))

  await waitFor(() => {
    expect(systemMocks.updateLLMSettings).toHaveBeenCalledWith({
      providerName: 'Primary OpenAI',
      baseUrl: 'https://api.openai.com/v1',
      apiKey: 'sk-test',
      model: 'gpt-4.1-mini',
    })
  })
  expect(await screen.findByText('LLM 设置已保存')).toBeInTheDocument()
  expect(await screen.findByText('LLM provider 已配置')).toBeInTheDocument()
})

test('system settings page defaults source build Agent off and persists an enabled setting', async () => {
  render(<SystemSettingsPage />)

  const sourceBuildAgentSwitch = await screen.findByRole('switch', { name: 'Agent 增强写源' })
  expect(sourceBuildAgentSwitch).not.toBeChecked()
  expect(
    screen.getByText('仅当确定性书源构建失败后才会调用 Agent。'),
  ).toBeInTheDocument()
  expect(screen.getByText('LLM provider 未配置')).toBeInTheDocument()

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

  const sourceBuildAgentSwitch = await screen.findByRole('switch', { name: 'Agent 增强写源' })
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

  expect(await screen.findByRole('switch', { name: 'Agent 增强写源' })).toBeChecked()
  expect(screen.getByText('LLM provider 已配置')).toBeInTheDocument()
})

test('system settings page keeps LLM panels available when Agent settings fail to load', async () => {
  systemMocks.getSourceBuildAgentSettings.mockRejectedValueOnce(new Error('settings unavailable'))
  render(<SystemSettingsPage />)

  expect(await screen.findByText('LLM API 配置')).toBeInTheDocument()
  expect(await screen.findByText('Provider 健康状态')).toBeInTheDocument()
  expect(await screen.findByText('配额策略')).toBeInTheDocument()
  expect(await screen.findByText('Primary OpenAI · 健康')).toBeInTheDocument()
  expect(await screen.findByRole('alert')).toHaveTextContent('加载写源 Agent 设置失败')
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

  const sourceBuildAgentSwitch = await screen.findByRole('switch', { name: 'Agent 增强写源' })
  expect(sourceBuildAgentSwitch).toBeDisabled()
  expect(systemMocks.updateSourceBuildAgentSettings).not.toHaveBeenCalled()

  resolveInitialSettings!(sourceBuildAgentSettings)
  await waitFor(() => expect(sourceBuildAgentSwitch).not.toBeDisabled())
})

test('system settings page announces Agent settings save failures as errors', async () => {
  systemMocks.updateSourceBuildAgentSettings.mockRejectedValueOnce(new Error('save unavailable'))
  render(<SystemSettingsPage />)

  const sourceBuildAgentSwitch = await screen.findByRole('switch', { name: 'Agent 增强写源' })
  fireEvent.click(sourceBuildAgentSwitch)

  expect(await screen.findByRole('alert')).toHaveTextContent('保存写源 Agent 设置失败')
})

test('system settings page saves interactive browser verification settings with bounded values', async () => {
  render(<SystemSettingsPage />)

  const browserSwitch = await screen.findByRole('switch', { name: '交互式浏览器验证' })
  const automaticSwitch = screen.getByRole('switch', { name: '自动尝试验证' })
  expect(browserSwitch).not.toBeChecked()
  expect(automaticSwitch).toBeDisabled()

  fireEvent.click(browserSwitch)
  expect(automaticSwitch).not.toBeDisabled()
  fireEvent.change(screen.getByLabelText('最大会话数'), { target: { value: '5' } })
  fireEvent.change(screen.getByLabelText('会话超时（秒）'), { target: { value: '30' } })
  fireEvent.click(screen.getByRole('button', { name: '保存交互式浏览器设置' }))

  await waitFor(() => {
    expect(systemMocks.updateInteractiveBrowserSettings).toHaveBeenCalledWith({
      enabled: true,
      automaticEnabled: true,
      maxSessions: 3,
      sessionTimeoutSeconds: 60,
    })
  })
  expect(await screen.findByRole('status')).toHaveTextContent('交互式浏览器设置已保存')
})

test('system settings page truncates fractional interactive browser limits before saving', async () => {
  render(<SystemSettingsPage />)

  await screen.findByRole('switch', { name: '交互式浏览器验证' })
  fireEvent.change(screen.getByLabelText('最大会话数'), { target: { value: '1.5' } })
  fireEvent.change(screen.getByLabelText('会话超时（秒）'), { target: { value: '300.9' } })
  fireEvent.click(screen.getByRole('button', { name: '保存交互式浏览器设置' }))

  await waitFor(() => {
    expect(systemMocks.updateInteractiveBrowserSettings).toHaveBeenCalledWith({
      enabled: false,
      automaticEnabled: true,
      maxSessions: 1,
      sessionTimeoutSeconds: 300,
    })
  })
})

test('system settings page announces interactive browser settings save failures as errors', async () => {
  systemMocks.updateInteractiveBrowserSettings.mockRejectedValueOnce(new Error('save unavailable'))
  render(<SystemSettingsPage />)

  fireEvent.click(await screen.findByRole('switch', { name: '交互式浏览器验证' }))
  fireEvent.click(screen.getByRole('button', { name: '保存交互式浏览器设置' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('保存交互式浏览器设置失败')
})

test('system settings page keeps browser edits available after a save failure', async () => {
  systemMocks.updateInteractiveBrowserSettings.mockRejectedValueOnce(new Error('save unavailable'))
  render(<SystemSettingsPage />)

  fireEvent.click(await screen.findByRole('switch', { name: '交互式浏览器验证' }))
  fireEvent.change(screen.getByLabelText('最大会话数'), { target: { value: '2' } })
  fireEvent.change(screen.getByLabelText('会话超时（秒）'), { target: { value: '180' } })
  const saveButton = screen.getByRole('button', { name: '保存交互式浏览器设置' })
  fireEvent.click(saveButton)

  expect(await screen.findByRole('alert')).toHaveTextContent('保存交互式浏览器设置失败')
  expect(screen.queryByRole('button', { name: '重试交互式浏览器设置' })).not.toBeInTheDocument()
  expect(saveButton).not.toBeDisabled()

  fireEvent.click(saveButton)
  await waitFor(() => {
    expect(systemMocks.updateInteractiveBrowserSettings).toHaveBeenLastCalledWith({
      enabled: true,
      automaticEnabled: true,
      maxSessions: 2,
      sessionTimeoutSeconds: 180,
    })
  })
})

test('system settings page preserves unsaved browser edits when saving LLM settings', async () => {
  render(<SystemSettingsPage />)

  await screen.findByRole('switch', { name: '交互式浏览器验证' })
  const maximumSessions = screen.getByLabelText('最大会话数')
  fireEvent.change(maximumSessions, { target: { value: '2' } })
  expect(maximumSessions).toHaveValue(2)
  expect(systemMocks.getInteractiveBrowserSettings).toHaveBeenCalledTimes(1)

  fireEvent.change(screen.getByLabelText('基础 URL'), { target: { value: 'https://api.example.test/v1' } })
  fireEvent.click(screen.getByRole('button', { name: '保存 LLM 设置' }))

  expect(await screen.findByText('LLM 设置已保存')).toBeInTheDocument()
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })

  expect(systemMocks.getInteractiveBrowserSettings).toHaveBeenCalledTimes(1)
  expect(maximumSessions).toHaveValue(2)
})

test('system settings page disables interactive browser controls after load failure and retries', async () => {
  systemMocks.getInteractiveBrowserSettings
    .mockRejectedValueOnce(new Error('settings unavailable'))
    .mockResolvedValueOnce({
      ...interactiveBrowserSettings,
      data: {
        enabled: true,
        automaticEnabled: true,
        maxSessions: 2,
        sessionTimeoutSeconds: 240,
      },
    })
  render(<SystemSettingsPage />)

  const browserSwitch = await screen.findByRole('switch', { name: '交互式浏览器验证' })
  expect(await screen.findByRole('alert')).toHaveTextContent('加载交互式浏览器设置失败')
  expect(browserSwitch).toBeDisabled()
  expect(screen.getByRole('switch', { name: '自动尝试验证' })).toBeDisabled()
  expect(screen.getByLabelText('最大会话数')).toBeDisabled()
  expect(screen.getByLabelText('会话超时（秒）')).toBeDisabled()
  expect(screen.getByRole('button', { name: '保存交互式浏览器设置' })).toBeDisabled()

  fireEvent.click(screen.getByRole('button', { name: '重试交互式浏览器设置' }))

  await waitFor(() => expect(systemMocks.getInteractiveBrowserSettings).toHaveBeenCalledTimes(2))
  await waitFor(() => expect(browserSwitch).not.toBeDisabled())
  expect(browserSwitch).toBeChecked()
})

test('system settings page ignores stale interactive browser settings after effect cleanup', async () => {
  const initialLoad = deferred<typeof interactiveBrowserSettings>()
  const refreshedSettings = {
    ...interactiveBrowserSettings,
    data: {
      enabled: true,
      automaticEnabled: false,
      maxSessions: 2,
      sessionTimeoutSeconds: 240,
    },
  }
  systemMocks.getInteractiveBrowserSettings
    .mockImplementationOnce(() => initialLoad.promise)
    .mockResolvedValueOnce(refreshedSettings)
  render(
    <StrictMode>
      <SystemSettingsPage />
    </StrictMode>,
  )

  const browserSwitch = await screen.findByRole('switch', { name: '交互式浏览器验证' })
  await waitFor(() => expect(systemMocks.getInteractiveBrowserSettings).toHaveBeenCalledTimes(2))
  await waitFor(() => expect(browserSwitch).toBeChecked())

  await act(async () => {
    initialLoad.resolve(interactiveBrowserSettings)
    await initialLoad.promise
  })

  expect(browserSwitch).toBeChecked()
  expect(screen.getByLabelText('最大会话数')).toHaveValue(2)
})

test('ai tasks page shows provider and model for each task', async () => {
  render(<AITasksPage />)

  expect(await screen.findByText('Provider')).toBeInTheDocument()
  expect(await screen.findByText('模型')).toBeInTheDocument()
})
