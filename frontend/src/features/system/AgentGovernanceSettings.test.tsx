import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, vi } from 'vitest'

const settingsMocks = vi.hoisted(() => ({
  getSettingsSection: vi.fn(),
  saveSettingsSection: vi.fn(),
}))

vi.mock('@/api/modules/system', () => ({
  getSettingsSection: settingsMocks.getSettingsSection,
  saveSettingsSection: settingsMocks.saveSettingsSection,
}))

import { AgentGovernanceSettings } from './AgentGovernanceSettings'

const initialSection = {
  success: true,
  code: 'OK',
  message: 'loaded',
  data: {
    domain: 'agents',
    tab: 'governance',
    value: {
      automatic_publish_explicit: true,
      automatic_publish_inferred: false,
      minimum_inferred_evidence: 2,
      require_human_review_for_identity: true,
      require_human_review_for_conflicts: true,
    },
    version: 'v1',
    updated_at: '2026-07-16T00:00:00Z',
  },
  meta: {},
  trace_id: null,
}

beforeEach(() => {
  settingsMocks.getSettingsSection.mockReset().mockResolvedValue(initialSection)
  settingsMocks.saveSettingsSection.mockReset().mockResolvedValue({
    ...initialSection,
    data: {
      ...initialSection.data,
      version: 'v2',
      updated_at: '2026-07-16T01:00:00Z',
      value: {
        ...initialSection.data.value,
        minimum_inferred_evidence: 8,
      },
    },
  })
})

test('governance save replaces local edits with the server canonical value', async () => {
  render(<AgentGovernanceSettings />)

  const evidenceInput = await screen.findByLabelText('推断事实的最小证据片段数')
  fireEvent.change(evidenceInput, { target: { value: '999' } })
  fireEvent.click(screen.getByRole('button', { name: '保存治理设置' }))

  expect(await screen.findByText(/生效时间/)).toBeInTheDocument()
  expect(screen.getByDisplayValue('8')).toBeInTheDocument()
})
