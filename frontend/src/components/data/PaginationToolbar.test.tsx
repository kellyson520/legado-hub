import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { LanguageProvider, useLanguage } from '@/app/providers/LanguageProvider'
import { PaginationToolbar } from './PaginationToolbar'

function renderToolbar(overrides: Partial<React.ComponentProps<typeof PaginationToolbar>> = {}) {
  const props: React.ComponentProps<typeof PaginationToolbar> = {
    page: 1,
    totalPages: 2,
    total: 21,
    searchInput: '',
    appliedSearch: '',
    loading: false,
    onSearchInput: vi.fn(),
    onSearch: vi.fn(),
    onClearSearch: vi.fn(),
    onPageChange: vi.fn(),
    ...overrides,
  }
  render(<PaginationToolbar {...props} />)
  return props
}

describe('PaginationToolbar', () => {
  test('renders an accessible search input and submits the current value', () => {
    const props = renderToolbar({ searchInput: ' beta ' })

    expect(screen.getByLabelText('搜索书源')).toHaveValue(' beta ')
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))
    expect(props.onSearch).toHaveBeenCalledTimes(1)
  })

  test('clears search and navigates between pages', () => {
    const props = renderToolbar({ appliedSearch: 'beta' })

    fireEvent.click(screen.getByRole('button', { name: '清空' }))
    fireEvent.click(screen.getByRole('button', { name: '下一页' }))
    expect(props.onClearSearch).toHaveBeenCalledTimes(1)
    expect(props.onPageChange).toHaveBeenCalledWith(2)
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled()
  })

  test('disables both navigation and search controls while loading', () => {
    renderToolbar({ loading: true })

    expect(screen.getByRole('button', { name: '搜索' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled()
  })

  test('shows a no-result message when the loaded list is empty', () => {
    renderToolbar({ total: 0, totalPages: 1 })

    expect(screen.getByText('暂无匹配数据')).toBeInTheDocument()
  })

test('can delegate loading and empty labels while retaining the page summary', () => {
    renderToolbar({ loading: true, showLoadingLabel: false, showEmptyLabel: false })
    expect(screen.queryByText('正在加载…')).not.toBeInTheDocument()

    // Loaded, non-empty rows still own their page summary in the toolbar.
    renderToolbar({ total: 21, totalPages: 2, showLoadingLabel: false, showEmptyLabel: false })
    expect(screen.getByText('第 1 / 2 页，共 21 条')).toBeInTheDocument()
  })
})

test('updates built-in labels when the active locale changes', async () => {
  const props: React.ComponentProps<typeof PaginationToolbar> = {
    page: 1,
    totalPages: 2,
    total: 21,
    searchInput: '',
    appliedSearch: '',
    loading: false,
    onSearchInput: vi.fn(),
    onSearch: vi.fn(),
    onClearSearch: vi.fn(),
    onPageChange: vi.fn(),
  }

  function Switcher() {
    const { setLocale } = useLanguage()
    return <button type="button" onClick={() => setLocale('en-US')}>English</button>
  }

  render(
    <LanguageProvider>
      <Switcher />
      <PaginationToolbar {...props} />
    </LanguageProvider>
  )

  fireEvent.click(screen.getByRole('button', { name: 'English' }))
  expect(await screen.findByLabelText('Search sources')).toBeInTheDocument()
  expect(await screen.findByText('Page 1 / 2, 21 items')).toBeInTheDocument()
})
