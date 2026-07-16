import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'

const mocks = vi.hoisted(() => ({ getWorkSnapshot: vi.fn(), getEvidence: vi.fn() }))
vi.mock('@/api/modules/novelAnalysis', () => mocks)

import { WorkAnalysisPage } from './WorkAnalysisPage'

test('published claim opens exact evidence citation', async () => {
  mocks.getWorkSnapshot.mockResolvedValue({ success: true, data: { published_claims: [{ id: 'c1', subject_entity_id: '宁姚', predicate: 'alive', evidence_ids: ['span-1'] }], open_conflicts: [] } })
  mocks.getEvidence.mockResolvedValue({ success: true, data: { excerpt: '宁姚在雨中救下少年。', canonical_chapter_title: 'Chapter 12', content_sha256: 'hash' } })
  render(<MemoryRouter initialEntries={['/novel-analysis/work-1']}><Routes><Route path="/novel-analysis/:workId" element={<WorkAnalysisPage />} /></Routes></MemoryRouter>)

  fireEvent.click(await screen.findByRole('button', { name: /宁姚/ }))

  expect(await screen.findByText('Evidence excerpt')).toBeInTheDocument()
  expect(screen.getByText('Chapter 12')).toBeInTheDocument()
})
