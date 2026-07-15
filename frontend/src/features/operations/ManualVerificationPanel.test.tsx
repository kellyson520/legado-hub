import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

const browserMocks = vi.hoisted(() => ({
  getInteractiveBrowserSession: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      id: 'browser-1',
      state: 'awaiting_manual_verification',
      target_origin: 'https://books.example.test',
      expires_at: '2026-07-15T12:05:00Z',
    },
    meta: {},
    trace_id: null,
  }),
  createInteractiveBrowserRelayTicket: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: { relay_path: '/api/interactive-browser/sessions/browser-1/relay?token=once&owner_id=42' },
    meta: {},
    trace_id: null,
  }),
  cancelInteractiveBrowserSession: vi.fn(),
  continueInteractiveBrowserSession: vi.fn(),
}))

vi.mock('@/api/modules/interactiveBrowser', () => browserMocks)
vi.mock('@novnc/novnc/lib/rfb', () => ({ default: vi.fn(() => ({ disconnect: vi.fn() })) }))

import { ManualVerificationPanel } from './ManualVerificationPanel'

test('shows the authorised target host and manual controls', async () => {
  render(<ManualVerificationPanel sessionId="browser-1" onFinished={vi.fn()} />)

  expect(await screen.findByText(/books\.example\.test/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Continue validation' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Cancel and destroy session' })).toBeInTheDocument()
})
