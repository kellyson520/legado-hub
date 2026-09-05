import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getWorkSnapshot: vi.fn(), getEvidence: vi.fn(), getWorkTasks: vi.fn(), pauseAnalysisTask: vi.fn(), resumeAnalysisTask: vi.fn(),
  runAnalysisTask: vi.fn(),
}))
vi.mock('@/api/modules/novelAnalysis', () => mocks)

import { WorkAnalysisPage } from './WorkAnalysisPage'

test('published claim opens exact evidence citation', async () => {
  mocks.getWorkSnapshot.mockResolvedValue({ success: true, data: { published_claims: [{ id: 'c1', subject_entity_id: '宁姚', predicate: 'alive', evidence_ids: ['span-1'] }], open_conflicts: [] } })
  mocks.getEvidence.mockResolvedValue({ success: true, data: { excerpt: '宁姚在雨中救下少年。', canonical_chapter_title: 'Chapter 12', content_sha256: 'hash' } })
  mocks.getWorkTasks.mockResolvedValue({ success: true, data: { items: [] } })
  render(<MemoryRouter initialEntries={['/novel-analysis/work-1']}><Routes><Route path="/novel-analysis/:workId" element={<WorkAnalysisPage />} /></Routes></MemoryRouter>)

  fireEvent.click(await screen.findByRole('button', { name: /宁姚/ }))

  expect(await screen.findByText('证据摘录')).toBeInTheDocument()
  expect(screen.getByText('Chapter 12')).toBeInTheDocument()
})

test('queued task exposes a pause control and refreshes its status', async () => {
  mocks.getWorkSnapshot.mockResolvedValue({ success: true, data: { published_claims: [], candidate_claims: [], open_conflicts: [] } })
  mocks.getWorkTasks.mockResolvedValue({
    success: true,
    data: { items: [{ id: 'task-1', status: 'queued', tool_call_count: 1, policy: { max_tool_calls_per_task: 24 }, checkpoint: { selected_evidence_ids: ['span-1'] } }] },
  })
  mocks.pauseAnalysisTask.mockResolvedValue({
    success: true,
    data: { id: 'task-1', status: 'paused', tool_call_count: 1, policy: { max_tool_calls_per_task: 24 }, checkpoint: { selected_evidence_ids: ['span-1'] } },
  })
  render(<MemoryRouter initialEntries={['/novel-analysis/work-1']}><Routes><Route path="/novel-analysis/:workId" element={<WorkAnalysisPage />} /></Routes></MemoryRouter>)

  fireEvent.click(await screen.findByRole('button', { name: '暂停任务 task-1' }))

  expect(await screen.findByText('已暂停')).toBeInTheDocument()
  expect(mocks.pauseAnalysisTask).toHaveBeenCalledWith('task-1')
})

test('queued task can be run directly without enabling background automation', async () => {
  mocks.getWorkSnapshot.mockResolvedValue({ success: true, data: { published_claims: [], candidate_claims: [], open_conflicts: [] } })
  mocks.getWorkTasks.mockResolvedValue({ success: true, data: { items: [{ id: 'task-2', status: 'queued', tool_call_count: 0, policy: {}, checkpoint: { selected_evidence_ids: ['span-1'] } }] } })
  mocks.runAnalysisTask.mockResolvedValue({ success: true, data: { id: 'task-2', status: 'completed', tool_call_count: 0, policy: {}, checkpoint: { selected_evidence_ids: ['span-1'], outcomes: [] } } })
  render(<MemoryRouter initialEntries={['/novel-analysis/work-1']}><Routes><Route path="/novel-analysis/:workId" element={<WorkAnalysisPage />} /></Routes></MemoryRouter>)

  fireEvent.click(await screen.findByRole('button', { name: '运行任务 task-2' }))

  expect(await screen.findByText('已完成')).toBeInTheDocument()
  expect(mocks.runAnalysisTask).toHaveBeenCalledWith('task-2')
})
