import { render, screen } from '@testing-library/react'

import { StatusBadge } from './StatusBadge'

test('StatusBadge maps operational statuses to readable semantic variants', () => {
  render(
    <>
      <StatusBadge status="healthy" />
      <StatusBadge status="candidate" />
      <StatusBadge status="scheduled" />
      <StatusBadge status="failed" />
    </>,
  )

  expect(screen.getByText('健康')).toHaveClass('bg-emerald-500')
  expect(screen.getByText('候选')).toHaveClass('bg-amber-500')
  expect(screen.getByText('已计划')).toHaveClass('bg-amber-500')
  expect(screen.getByText('已失败')).toHaveClass('bg-destructive')
})
