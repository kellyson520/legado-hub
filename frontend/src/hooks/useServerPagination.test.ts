import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { useServerPagination } from './useServerPagination'

function envelope<T>(data: T[], meta: Record<string, unknown> = {}) {
  return {
    success: true,
    code: 'OK',
    message: 'ok',
    data,
    meta,
    trace_id: null,
  }
}

function row(id: string) {
  return { id }
}

describe('useServerPagination', () => {
  test('loads the first page and exposes normalized rows', async () => {
    const load = vi.fn().mockResolvedValue(envelope([row('one')], { page: 1, page_size: 2, total: 1, total_pages: 1 }))
    const { result } = renderHook(() => useServerPagination({ pageSize: 2, load }))

    await waitFor(() => expect(load).toHaveBeenCalledWith({ page: 1, pageSize: 2, search: '' }))
    await waitFor(() => expect(result.current.rows).toEqual([row('one')]))
    expect(result.current.meta.total).toBe(1)
  })

  test('replaces rows when navigating to another page', async () => {
    const load = vi.fn().mockImplementation(({ page }: { page: number }) => (
      Promise.resolve(envelope([row(page === 1 ? 'one' : 'two')], { page, page_size: 1, total: 2, total_pages: 2 }))
    ))
    const { result } = renderHook(() => useServerPagination({ pageSize: 1, load }))

    await waitFor(() => expect(result.current.rows).toEqual([row('one')]))
    act(() => result.current.goToPage(2))
    await waitFor(() => expect(result.current.rows).toEqual([row('two')]))
    expect(result.current.rows).not.toContainEqual(row('one'))
    expect(load).toHaveBeenLastCalledWith({ page: 2, pageSize: 1, search: '' })
  })

  test('trims search and resets to page one', async () => {
    const load = vi.fn().mockResolvedValue(envelope([row('beta')], { page: 1, page_size: 2, total: 1, total_pages: 1 }))
    const { result } = renderHook(() => useServerPagination({ pageSize: 2, load }))

    await waitFor(() => expect(load).toHaveBeenCalledTimes(1))
    act(() => result.current.submitSearch(' beta '))
    await waitFor(() => expect(load).toHaveBeenLastCalledWith({ page: 1, pageSize: 2, search: 'beta' }))
    expect(result.current.appliedSearch).toBe('beta')
  })

  test('retries the failed page and search request', async () => {
    const load = vi.fn()
      .mockResolvedValueOnce(envelope([row('one')], { page: 1, page_size: 1, total: 2, total_pages: 2 }))
      .mockRejectedValueOnce(new Error('page unavailable'))
      .mockResolvedValueOnce(envelope([row('two')], { page: 2, page_size: 1, total: 2, total_pages: 2 }))
    const { result } = renderHook(() => useServerPagination({ pageSize: 1, load }))

    await waitFor(() => expect(result.current.rows).toEqual([row('one')]))
    act(() => result.current.goToPage(2))
    await waitFor(() => expect(result.current.error?.message).toBe('page unavailable'))
    act(() => result.current.retry())
    await waitFor(() => expect(result.current.rows).toEqual([row('two')]))
    expect(load).toHaveBeenLastCalledWith({ page: 2, pageSize: 1, search: '' })
  })

  test('ignores a stale response after a newer request resolves', async () => {
    let resolveFirst!: (value: ReturnType<typeof envelope<typeof row>> | PromiseLike<ReturnType<typeof envelope<typeof row>>>) => void
    const first = new Promise((resolve) => { resolveFirst = resolve })
    const load = vi.fn()
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce(envelope([row('new')], { page: 1, page_size: 1, total: 1, total_pages: 1 }))
    const { result } = renderHook(() => useServerPagination({ pageSize: 1, load }))

    act(() => result.current.submitSearch('new'))
    await waitFor(() => expect(result.current.rows).toEqual([row('new')]))
    resolveFirst(envelope([row('old')], { page: 1, page_size: 1, total: 1, total_pages: 1 }))
    await Promise.resolve()
    expect(result.current.rows).toEqual([row('new')])
  })

  test('does not update state after unmount', async () => {
    let resolve!: (value: ReturnType<typeof envelope<typeof row>> | PromiseLike<ReturnType<typeof envelope<typeof row>>>) => void
    const load = vi.fn().mockReturnValue(new Promise((nextResolve) => { resolve = nextResolve }))
    const { unmount } = renderHook(() => useServerPagination({ pageSize: 1, load }))

    unmount()
    resolve(envelope([row('late')], { page: 1, page_size: 1, total: 1, total_pages: 1 }))
    await Promise.resolve()
  })
})
