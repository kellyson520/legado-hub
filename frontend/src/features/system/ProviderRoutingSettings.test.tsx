import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  listProviders: vi.fn(),
  createProvider: vi.fn(),
  updateProvider: vi.fn(),
  discoverProviderModels: vi.fn(),
  getProviderRoute: vi.fn(),
  updateProviderRoute: vi.fn(),
}))

vi.mock('@/api/modules/system', () => ({
  listProviders: mocks.listProviders,
  createProvider: mocks.createProvider,
  updateProvider: mocks.updateProvider,
  discoverProviderModels: mocks.discoverProviderModels,
  getProviderRoute: mocks.getProviderRoute,
  updateProviderRoute: mocks.updateProviderRoute,
}))

import { ProviderRoutingSettings } from './ProviderRoutingSettings'

const envelope = <T,>(data: T) => ({ success: true, code: 'OK', message: 'ok', data, meta: {}, trace_id: null })

const primary = {
  id: 'primary',
  name: 'Primary',
  baseUrl: 'https://primary.example/v1',
  defaultModel: 'gpt-primary',
  enabled: true,
  apiKeyConfigured: true,
  apiKeyMasked: '••••1234',
  status: 'enabled',
}

const backup = {
  id: 'backup',
  name: 'Backup',
  baseUrl: 'https://backup.example/v1',
  defaultModel: 'gpt-backup',
  enabled: true,
  apiKeyConfigured: true,
  apiKeyMasked: '••••5678',
  status: 'enabled',
}

beforeEach(() => {
  mocks.listProviders.mockReset().mockResolvedValue(envelope([primary, backup]))
  mocks.createProvider.mockReset()
  mocks.updateProvider.mockReset().mockResolvedValue(envelope(primary))
  mocks.discoverProviderModels.mockReset().mockResolvedValue(envelope(['gpt-primary', 'gpt-primary-plus']))
  mocks.getProviderRoute.mockReset().mockImplementation((group: string) =>
    Promise.resolve(envelope({ group, entries: group === 'ai' ? [{ providerAccountId: 'primary', providerName: 'Primary', model: 'gpt-primary', priority: 0, enabled: true }] : [] })),
  )
  mocks.updateProviderRoute.mockReset().mockImplementation((group: string, payload: { entries: unknown[] }) =>
    Promise.resolve(envelope({ group, entries: payload.entries })),
  )
})

test('editing a channel saves a blank key safely and announces the masked configured state', async () => {
  const onProviderSaved = vi.fn().mockResolvedValue(undefined)
  render(<ProviderRoutingSettings onProviderSaved={onProviderSaved} />)

  fireEvent.click(await screen.findByRole('button', { name: '编辑 Primary' }))
  fireEvent.change(screen.getByLabelText('渠道默认模型'), { target: { value: 'gpt-primary-v2' } })
  fireEvent.click(screen.getByRole('button', { name: '保存渠道' }))

  await waitFor(() => {
    expect(mocks.updateProvider).toHaveBeenCalledWith('primary', {
      name: 'Primary',
      baseUrl: 'https://primary.example/v1',
      apiKey: '',
      defaultModel: 'gpt-primary-v2',
      enabled: true,
    })
  })
  expect(await screen.findByText('API Key：已配置（••••1234）')).toBeInTheDocument()
  expect(onProviderSaved).toHaveBeenCalledTimes(1)
})

test('channel model discovery and functional route fallback ordering are available without a page refresh', async () => {
  render(<ProviderRoutingSettings onProviderSaved={vi.fn()} />)

  fireEvent.click(await screen.findByRole('button', { name: '获取 Primary 的模型' }))
  expect(await screen.findByText('gpt-primary-plus')).toBeInTheDocument()

  fireEvent.change(screen.getByLabelText('AI 分析 的 Provider'), { target: { value: 'backup' } })
  fireEvent.change(screen.getByLabelText('AI 分析 的模型'), { target: { value: 'gpt-backup' } })
  fireEvent.click(screen.getByRole('button', { name: '为 AI 分析 添加备用项' }))

  await waitFor(() => {
    expect(mocks.updateProviderRoute).toHaveBeenCalledWith('ai', {
      entries: [
        { providerAccountId: 'primary', model: 'gpt-primary', enabled: true },
        { providerAccountId: 'backup', model: 'gpt-backup', enabled: true },
      ],
    })
  })

  fireEvent.click(screen.getByRole('button', { name: '将 Backup 上移' }))
  await waitFor(() => {
    expect(mocks.updateProviderRoute).toHaveBeenLastCalledWith('ai', {
      entries: [
        { providerAccountId: 'backup', model: 'gpt-backup', enabled: true },
        { providerAccountId: 'primary', model: 'gpt-primary', enabled: true },
      ],
    })
  })
})

test('an edited channel can be disabled without rewriting its stored key', async () => {
  render(<ProviderRoutingSettings onProviderSaved={vi.fn()} />)

  fireEvent.click(await screen.findByRole('button', { name: '编辑 Primary' }))
  fireEvent.click(screen.getByLabelText('启用渠道'))
  fireEvent.click(screen.getByRole('button', { name: '保存渠道' }))

  await waitFor(() => {
    expect(mocks.updateProvider).toHaveBeenCalledWith('primary', {
      name: 'Primary',
      baseUrl: 'https://primary.example/v1',
      apiKey: '',
      defaultModel: 'gpt-primary',
      enabled: false,
    })
  })
})

test('a new channel can be saved before a model is selected for discovery', async () => {
  mocks.createProvider.mockResolvedValueOnce(envelope({
    id: 'new-provider',
    name: 'Discovery first',
    baseUrl: 'https://discovery.example/v1',
    defaultModel: '',
    enabled: true,
    apiKeyConfigured: true,
    apiKeyMasked: '••••9999',
    status: 'enabled',
  }))
  render(<ProviderRoutingSettings onProviderSaved={vi.fn()} />)

  fireEvent.click(await screen.findByRole('button', { name: '添加渠道' }))
  fireEvent.change(screen.getByLabelText('渠道名称'), { target: { value: 'Discovery first' } })
  fireEvent.change(screen.getByLabelText('渠道基础 URL'), { target: { value: 'https://discovery.example/v1' } })
  fireEvent.change(screen.getByLabelText('渠道 API Key'), { target: { value: 'sk-discovery' } })
  fireEvent.click(screen.getByRole('button', { name: '保存渠道' }))

  await waitFor(() => {
    expect(mocks.createProvider).toHaveBeenCalledWith({
      name: 'Discovery first',
      baseUrl: 'https://discovery.example/v1',
      apiKey: 'sk-discovery',
      defaultModel: '',
      enabled: true,
    })
  })
})

test('keeps saved provider controls available when route loading fails', async () => {
  mocks.getProviderRoute.mockRejectedValue(new Error('route API unavailable'))
  render(<ProviderRoutingSettings onProviderSaved={vi.fn()} />)

  expect(await screen.findByRole('button', { name: '获取 Primary 的模型' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '编辑 Primary' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '为 AI 分析 添加备用项' })).toBeDisabled()
  expect(await screen.findByText(/Provider 路由暂时不可用/)).toBeInTheDocument()
})

test('shows the provider credential error when model discovery is rejected', async () => {
  mocks.discoverProviderModels.mockRejectedValue({
    isAxiosError: true,
    response: { data: { detail: 'Provider authentication failed; update the API key' } },
  })
  render(<ProviderRoutingSettings onProviderSaved={vi.fn()} />)

  fireEvent.click(await screen.findByRole('button', { name: '获取 Primary 的模型' }))

  expect(await screen.findByText('Provider 身份验证失败；请更新 API Key')).toBeInTheDocument()
})
