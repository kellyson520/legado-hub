import { describe, expect, test } from 'vitest'

import type { AdminListParams } from './modules/admin'
import type { AIListParams } from './modules/ai'
import type { EngineListParams } from './modules/engine'
import type { OperationListParams } from './modules/operations'
import type { NovelListParams } from './modules/novel'
import type { SourceHealthListParams } from './modules/sourceHealth'
import type { SourceListParams } from './modules/sources'
import type { TranslationListParams } from './modules/translation'
import type { PaginatedQueryParams, PaginatedStatusQueryParams } from './types'

describe('shared paginated query contracts', () => {
  test('accept common page, search, and status parameters', () => {
    const query: PaginatedQueryParams = {
      page: 2,
      page_size: 20,
      search: 'source',
    }
    const statusQuery: PaginatedStatusQueryParams = {
      ...query,
      status: 'enabled',
    }

    expect(query).toEqual({ page: 2, page_size: 20, search: 'source' })
    expect(statusQuery).toEqual({ ...query, status: 'enabled' })
  })

  test('keeps module-specific parameter names compatible with the shared contracts', () => {
    const query: PaginatedQueryParams = { page: 1, page_size: 20, search: 'source' }
    const statusQuery: PaginatedStatusQueryParams = { ...query, status: 'active' }
    const moduleQueries: Array<PaginatedQueryParams | PaginatedStatusQueryParams> = [
      {} as AdminListParams,
      {} as AIListParams,
      {} as EngineListParams,
      {} as OperationListParams,
      {} as NovelListParams,
      {} as SourceListParams,
      {} as SourceHealthListParams,
      {} as TranslationListParams,
    ]

    expect(moduleQueries).toHaveLength(8)
    expect(statusQuery).toMatchObject(query)
  })
})
