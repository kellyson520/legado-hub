import { describe, expect, test } from 'vitest'

import { normalizePageMeta, toPaginatedQueryParams } from './pagination'

describe('normalizePageMeta', () => {
  test('keeps valid server metadata and search', () => {
    expect(normalizePageMeta(
      { page: 2, page_size: 20, total: 41, total_pages: 3, search: 'beta' },
      1,
      20,
      20,
    )).toEqual({
      page: 2,
      page_size: 20,
      total: 41,
      total_pages: 3,
      search: 'beta',
    })
  })

  test('falls back to requested page and row count when metadata is missing', () => {
    expect(normalizePageMeta({}, 2, 20, 21)).toEqual({
      page: 2,
      page_size: 20,
      total: 21,
      total_pages: 2,
      search: undefined,
    })
  })

  test('keeps an empty result on a safe first page', () => {
    expect(normalizePageMeta({ total: 0 }, 4, 20, 0)).toEqual({
      page: 4,
      page_size: 20,
      total: 0,
      total_pages: 1,
      search: undefined,
    })
  })

  test('rejects fractional and non-positive numeric metadata', () => {
    expect(normalizePageMeta(
      { page: 2.5, page_size: 0, total: -1, total_pages: Number.NaN },
      3,
      20,
      5,
    )).toEqual({
      page: 3,
      page_size: 20,
      total: 5,
      total_pages: 1,
      search: undefined,
    })
  })
})

describe('toPaginatedQueryParams', () => {
  test('maps hook page requests to the backend query contract', () => {
    expect(toPaginatedQueryParams({ page: 3, pageSize: 25, search: '  beta  ' })).toEqual({
      page: 3,
      page_size: 25,
      search: '  beta  ',
    })
  })
})
