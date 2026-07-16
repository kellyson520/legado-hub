import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { PaginatedListControls } from './PaginatedListControls'

function createPagination(overrides: Partial<React.ComponentProps<typeof PaginatedListControls>['pagination']> = {}) {
  return {
    meta: { page: 1, page_size: 20, total: 12, total_pages: 1 },
    searchInput: '',
    appliedSearch: '',
    loading: false,
    error: null,
    setSearchInput: vi.fn(),
    submitSearch: vi.fn(),
    clearSearch: vi.fn(),
    goToPage: vi.fn(),
    retry: vi.fn(),
    ...overrides,
  }
}

describe('PaginatedListControls', () => {
  test('composes pagination controls with the shared list status', () => {
    const pagination = createPagination({
      meta: { page: 1, page_size: 20, total: 0, total_pages: 0 },
      error: new Error('network'),
    })

    render(
      <PaginatedListControls
        pagination={pagination}
        empty={false}
        loadingLabel="正在加载书源…"
        errorLabel="加载书源失败"
        emptyLabel="暂无书源"
        searchLabel="搜索书源"
      />
    )

    expect(screen.getByLabelText('搜索书源')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('加载书源失败')
    expect(screen.queryByText('暂无匹配数据')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(pagination.retry).toHaveBeenCalledTimes(1)
  })
})
