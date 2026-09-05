import { fireEvent, render, screen } from '@testing-library/react'

import { ListStatus } from './ListStatus'

test('ListStatus renders the loading state', () => {
  render(
    <ListStatus
      loading
      error={null}
      empty={false}
      onRetry={() => undefined}
      loadingLabel="正在加载…"
      errorLabel="加载失败"
      emptyLabel="暂无数据"
    />
  )

  expect(screen.getByText('正在加载…')).toBeInTheDocument()
})

test('ListStatus renders a retryable error state', () => {
  const onRetry = vi.fn()
  render(
    <ListStatus
      loading={false}
      error={new Error('network')}
      empty={false}
      onRetry={onRetry}
      loadingLabel="正在加载…"
      errorLabel="加载失败"
      emptyLabel="暂无数据"
    />
  )

  expect(screen.getByRole('alert')).toHaveTextContent('加载失败')
  fireEvent.click(screen.getByRole('button', { name: '重试' }))
  expect(onRetry).toHaveBeenCalledTimes(1)
})

test('ListStatus renders empty only after loading and error are clear', () => {
  render(
    <ListStatus
      loading={false}
      error={null}
      empty
      onRetry={() => undefined}
      loadingLabel="正在加载…"
      errorLabel="加载失败"
      emptyLabel="暂无数据"
    />
  )

  expect(screen.getByText('暂无数据')).toBeInTheDocument()
})

test('ListStatus renders nothing for a populated list', () => {
  const { container } = render(
    <ListStatus
      loading={false}
      error={null}
      empty={false}
      onRetry={() => undefined}
      loadingLabel="正在加载…"
      errorLabel="加载失败"
      emptyLabel="暂无数据"
    />
  )

  expect(container).toBeEmptyDOMElement()
})
