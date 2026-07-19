import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test } from 'vitest'

const featureRoot = resolve(process.cwd(), 'src/features')
const read = (relativePath: string) => readFileSync(resolve(featureRoot, relativePath), 'utf8')

describe('console component boundaries', () => {
  test.each([
    'operations/JobsPage.tsx',
    'operations/ReviewQueuePage.tsx',
    'operations/EventDeliveriesPage.tsx',
    'operations/SourceBuildsPage.tsx',
    'sources/SourceHealthDetailPage.tsx',
  ])('%s delegates table markup to DataTable', (relativePath) => {
    expect(read(relativePath)).not.toMatch(/<table\b/)
    expect(read(relativePath)).toContain('@/components/data/DataTable')
  })

  test('production feature modules do not call fetch directly', () => {
    const sourceFiles = [
      'operations/JobsPage.tsx',
      'operations/ReviewQueuePage.tsx',
      'operations/EventDeliveriesPage.tsx',
      'operations/SourceBuildsPage.tsx',
      'sources/SourceHealthDetailPage.tsx',
    ]
    for (const relativePath of sourceFiles) {
      expect(read(relativePath)).not.toMatch(/\bfetch\s*\(/)
    }
  })
})
