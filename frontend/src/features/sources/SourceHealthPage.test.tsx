import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

vi.mock('@/api/modules/sourceHealth', () => ({
  listSourceHealth: vi.fn(),
  probeSourceHealth: vi.fn(),
  probeSourceHealthBatch: vi.fn(),
  recoverSourceHealth: vi.fn(),
}))

import { listSourceHealth, probeSourceHealth, probeSourceHealthBatch, recoverSourceHealth } from '@/api/modules/sourceHealth'
import { SourceHealthPage } from './SourceHealthPage'

const pageOneRows = [
  {
    source_id: 7,
    source_name: '七猫小说',
    source_url: 'https://www.qimao.com',
    health_status: 'healthy',
    search_status: 'ok',
    toc_status: 'ok',
    content_status: 'ok',
    failure_reason: '',
    route_policy: 'allow',
  },
  {
    source_id: 4,
    source_name: '起点读书限免+本章说',
    source_url: 'https://www.qidian.com',
    health_status: 'blocked',
    search_status: 'failed',
    toc_status: 'skipped',
    content_status: 'skipped',
    failure_reason: 'token_missing',
    route_policy: 'skip',
  },
]

const pageTwoRows = [{
  source_id: 22,
  source_name: '第二页书源',
  source_url: 'https://page-two.example.test',
  health_status: 'dead',
  search_status: 'failed',
  toc_status: 'skipped',
  content_status: 'skipped',
  failure_reason: 'unreachable',
  route_policy: 'skip',
}]

function healthResponse(page: number, data = page === 2 ? pageTwoRows : pageOneRows) {
  return {
    success: true,
    code: 'OK',
    message: 'ok',
    data,
    meta: {
      page,
      page_size: 20,
      total: 21,
      status_counts: {
        total: 21,
        healthy: 12,
        degraded: 2,
        blocked: 3,
        dead: 1,
        unprobed: 2,
        unknown: 1,
        disabled: 0,
      },
    },
    trace_id: null,
  }
}

function mutationResponse() {
  return {
    success: true,
    code: 'OK',
    message: 'ok',
    data: {},
    meta: {},
    trace_id: null,
  }
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.mocked(listSourceHealth).mockReset()
  vi.mocked(listSourceHealth).mockImplementation((params: { page?: number } = {}) => (
    Promise.resolve(healthResponse(params.page ?? 1))
  ))
  vi.mocked(probeSourceHealth).mockReset()
  vi.mocked(probeSourceHealth).mockResolvedValue(mutationResponse())
  vi.mocked(probeSourceHealthBatch).mockReset()
  vi.mocked(probeSourceHealthBatch).mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [],
    meta: { total: 0 },
    trace_id: null,
  })
  vi.mocked(recoverSourceHealth).mockReset()
  vi.mocked(recoverSourceHealth).mockResolvedValue(mutationResponse())
})

afterEach(() => {
  vi.restoreAllMocks()
})

test('source health page shows stage statuses, page-scoped summaries, and unique source actions', async () => {
  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('书源健康控制台')).toBeInTheDocument()
  expect(await screen.findByText('token_missing')).toBeInTheDocument()
  expect(screen.getByText('总计： 21')).toBeInTheDocument()
  expect(screen.getByText('本页健康： 1')).toBeInTheDocument()
  expect(screen.getByText('本页阻断： 1')).toBeInTheDocument()
  expect(screen.getByText('本页失效： 0')).toBeInTheDocument()
  expect(screen.getByText('本页未探测： 0')).toBeInTheDocument()
  expect(screen.getByText('总健康： 12')).toBeInTheDocument()
  expect(screen.getByText('总降级： 2')).toBeInTheDocument()
  expect(screen.getByText('总阻断： 3')).toBeInTheDocument()
  expect(screen.getByText('总失效： 1')).toBeInTheDocument()
  expect(screen.getByText('总未探测： 2')).toBeInTheDocument()
  expect(screen.getByText('总未知： 1')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '探测书源 七猫小说' })).toBeEnabled()
  expect(screen.getByRole('button', { name: '恢复书源 七猫小说' })).toBeEnabled()
  expect(
    (await screen.findAllByRole('link', { name: '查看书源详情' })).find(
      (link) => link.getAttribute('href') === '/sources/health/7'
    )
  ).toBeDefined()
})

test('source health page separates unprobed rows from unknown errors', async () => {
  const response = healthResponse(1, [
    {
      ...pageOneRows[0],
      source_id: 30,
      source_name: '尚未探测书源',
      health_status: 'unknown',
      search_status: 'unknown',
      toc_status: 'unknown',
      content_status: 'unknown',
      failure_reason: 'not_probed',
    },
    {
      ...pageOneRows[1],
      source_id: 31,
      source_name: '解析异常书源',
      health_status: 'unknown',
      failure_reason: 'unknown_error',
    },
  ])
  response.meta.total = 2
  response.meta.status_counts = {
    total: 2,
    healthy: 0,
    degraded: 0,
    blocked: 0,
    dead: 0,
    unprobed: 1,
    unknown: 1,
    disabled: 0,
  }
  vi.mocked(listSourceHealth).mockResolvedValueOnce(response)

  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('尚未探测书源')).toBeInTheDocument()
  expect(screen.getByText('本页未探测： 1')).toBeInTheDocument()
  expect(screen.getByText('本页未知： 1')).toBeInTheDocument()
  expect(screen.getByText('总未探测： 1')).toBeInTheDocument()
  expect(screen.getByText('总未知： 1')).toBeInTheDocument()
})

test('source health page separates disabled sources from unprobed sources', async () => {
  const response = healthResponse(1, [{
    ...pageOneRows[0],
    source_id: 32,
    source_name: '已禁用书源',
    health_status: 'disabled',
    search_status: 'skipped',
    toc_status: 'skipped',
    content_status: 'skipped',
    failure_reason: 'disabled',
    route_policy: 'skip',
  }])
  response.meta.total = 1
  response.meta.status_counts = {
    total: 1,
    healthy: 0,
    degraded: 0,
    blocked: 0,
    dead: 0,
    unprobed: 0,
    unknown: 0,
    disabled: 1,
  }
  vi.mocked(listSourceHealth).mockResolvedValueOnce(response)

  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('已禁用书源')).toBeInTheDocument()
  expect(screen.getByText('本页禁用： 1')).toBeInTheDocument()
  expect(screen.getByText('总禁用： 1')).toBeInTheDocument()
  expect(screen.getByText('总未探测： 0')).toBeInTheDocument()
})

test('source health page does not present page counts as full distribution when metadata is unavailable', async () => {
  const response = healthResponse(1)
  delete (response.meta as { status_counts?: unknown }).status_counts
  vi.mocked(listSourceHealth).mockResolvedValueOnce(response)

  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('全量健康统计（状态分布不可用）')).toBeInTheDocument()
  expect(screen.getByText('总计： 21')).toBeInTheDocument()
  expect(screen.getByText('总健康： —')).toBeInTheDocument()
  expect(screen.getByText('本页健康： 1')).toBeInTheDocument()
})

test('smart probe button probes every visible source instead of only refreshing the list', async () => {
  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('七猫小说')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '智能探测本页' }))

  await waitFor(() => {
    expect(probeSourceHealthBatch).toHaveBeenCalledWith([7, 4], ['捞尸人', '斗罗大陆', '剑来'])
  })
})

test('source health page uses API metadata to navigate the inventory one page at a time', async () => {
  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('总计： 21')).toBeInTheDocument()
  expect(screen.getByText('第 1 / 2 页，共 21 条')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled()

  fireEvent.click(screen.getByRole('button', { name: '下一页' }))

  await waitFor(() => {
    expect(listSourceHealth).toHaveBeenLastCalledWith({ page: 2, page_size: 20, search: '' })
  })
  expect(await screen.findByText('第二页书源')).toBeInTheDocument()
  expect(screen.getByText('第 2 / 2 页，共 21 条')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled()
})

test('source health page stops loading and offers a retry when its request fails', async () => {
  vi.mocked(listSourceHealth).mockRejectedValueOnce(new Error('network unavailable'))
  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByRole('alert')).toHaveTextContent('加载书源健康状态失败，请重试。')
  expect(screen.queryByText('正在加载')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '重试' }))

  await waitFor(() => {
    expect(listSourceHealth).toHaveBeenLastCalledWith({ page: 1, page_size: 20, search: '' })
  })
  expect(await screen.findByText('七猫小说')).toBeInTheDocument()
})

test('a failed page request retries the failed page and keeps actions on the retried page', async () => {
  let pageTwoAttempts = 0
  vi.mocked(listSourceHealth).mockImplementation((params: { page?: number } = {}) => {
    if ((params.page ?? 1) === 2) {
      pageTwoAttempts += 1
      return pageTwoAttempts === 1
        ? Promise.reject(new Error('page two unavailable'))
        : Promise.resolve(healthResponse(2))
    }
    return Promise.resolve(healthResponse(1))
  })
  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('七猫小说')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '下一页' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('加载书源健康状态失败，请重试。')
  expect(screen.getByText('第 1 / 2 页，共 21 条')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: '重试' }))
  await waitFor(() => {
    expect(listSourceHealth).toHaveBeenLastCalledWith({ page: 2, page_size: 20, search: '' })
  })
  expect(await screen.findByText('第二页书源')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: '探测书源 第二页书源' }))
  await waitFor(() => {
    expect(listSourceHealth).toHaveBeenLastCalledWith({ page: 2, page_size: 20, search: '' })
  })
})

test.each(['probe', 'recover'] as const)('%s completion preserves the latest in-flight navigation', async (verb) => {
  const mutation = deferred<ReturnType<typeof mutationResponse>>()
  const firstPageTwo = deferred<ReturnType<typeof healthResponse>>()
  const latestPageTwo = deferred<ReturnType<typeof healthResponse>>()
  let pageTwoRequests = 0
  if (verb === 'probe') vi.mocked(probeSourceHealth).mockReturnValueOnce(mutation.promise)
  else vi.mocked(recoverSourceHealth).mockReturnValueOnce(mutation.promise)
  vi.mocked(listSourceHealth).mockImplementation((params: { page?: number } = {}) => {
    if ((params.page ?? 1) === 1) return Promise.resolve(healthResponse(1))
    pageTwoRequests += 1
    return pageTwoRequests === 1 ? firstPageTwo.promise : latestPageTwo.promise
  })
  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('七猫小说')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: verb === 'probe' ? '探测书源 七猫小说' : '恢复书源 七猫小说' }))
  expect(screen.getByRole('button', { name: verb === 'probe' ? '探测书源 七猫小说' : '恢复书源 七猫小说' })).toBeDisabled()
  expect(screen.getByRole('button', { name: verb === 'probe' ? '恢复书源 七猫小说' : '探测书源 七猫小说' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '探测书源 起点读书限免+本章说' })).toBeEnabled()

  fireEvent.click(screen.getByRole('button', { name: '下一页' }))
  await waitFor(() => {
    expect(listSourceHealth).toHaveBeenLastCalledWith({ page: 2, page_size: 20, search: '' })
  })

  mutation.resolve(mutationResponse())
  await waitFor(() => expect(pageTwoRequests).toBe(2))
  latestPageTwo.resolve(healthResponse(2, [{ ...pageTwoRows[0], source_name: `最新第二页书源-${verb}` }]))
  expect(await screen.findByText(`最新第二页书源-${verb}`)).toBeInTheDocument()

  firstPageTwo.resolve(healthResponse(2, [{ ...pageTwoRows[0], source_name: '过期第二页书源' }]))
  await Promise.resolve()
  expect(screen.getByText(`最新第二页书源-${verb}`)).toBeInTheDocument()
  expect(screen.queryByText('过期第二页书源')).not.toBeInTheDocument()
  expect(screen.getByText('第 2 / 2 页，共 21 条')).toBeInTheDocument()
})

test('a rejected probe keeps the current page visible and re-enables its actions', async () => {
  vi.mocked(probeSourceHealth).mockRejectedValueOnce(new Error('probe failed'))
  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('七猫小说')).toBeInTheDocument()
  const probeButton = screen.getByRole('button', { name: '探测书源 七猫小说' })
  fireEvent.click(probeButton)

  expect(await screen.findByRole('alert')).toHaveTextContent('无法探测七猫小说，请重试。')
  expect(screen.getByText('七猫小说')).toBeInTheDocument()
  expect(screen.getByText('第 1 / 2 页，共 21 条')).toBeInTheDocument()
  expect(probeButton).toBeEnabled()
})

test('a rejected recovery keeps the current page visible and re-enables its actions', async () => {
  vi.mocked(recoverSourceHealth).mockRejectedValueOnce(new Error('recovery failed'))
  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('七猫小说')).toBeInTheDocument()
  const recoverButton = screen.getByRole('button', { name: '恢复书源 七猫小说' })
  fireEvent.click(recoverButton)

  expect(await screen.findByRole('alert')).toHaveTextContent('无法恢复七猫小说，请重试。')
  expect(screen.getByText('七猫小说')).toBeInTheDocument()
  expect(screen.getByText('第 1 / 2 页，共 21 条')).toBeInTheDocument()
  expect(recoverButton).toBeEnabled()
})

test('unmounting during a list request ignores its deferred response', async () => {
  const pendingList = deferred<ReturnType<typeof healthResponse>>()
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
  vi.mocked(listSourceHealth).mockReturnValueOnce(pendingList.promise)
  const { unmount } = render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  await waitFor(() => expect(listSourceHealth).toHaveBeenCalledTimes(1))
  unmount()
  pendingList.resolve(healthResponse(1))
  await Promise.resolve()
  await Promise.resolve()

  expect(listSourceHealth).toHaveBeenCalledTimes(1)
  expect(consoleError).not.toHaveBeenCalled()
})

test('unmounting during a probe prevents its deferred success from reloading', async () => {
  const pendingProbe = deferred<ReturnType<typeof mutationResponse>>()
  vi.mocked(probeSourceHealth).mockReturnValueOnce(pendingProbe.promise)
  const { unmount } = render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('七猫小说')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '探测书源 七猫小说' }))
  unmount()
  pendingProbe.resolve(mutationResponse())
  await Promise.resolve()
  await Promise.resolve()

  expect(listSourceHealth).toHaveBeenCalledTimes(1)
})

test('unmounting during a rejected recovery does not update the removed page', async () => {
  const pendingRecovery = deferred<ReturnType<typeof mutationResponse>>()
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
  vi.mocked(recoverSourceHealth).mockReturnValueOnce(pendingRecovery.promise)
  const { unmount } = render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('七猫小说')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '恢复书源 七猫小说' }))
  unmount()
  pendingRecovery.reject(new Error('recovery failed'))
  await Promise.resolve()
  await Promise.resolve()

  expect(listSourceHealth).toHaveBeenCalledTimes(1)
  expect(consoleError).not.toHaveBeenCalled()
})
