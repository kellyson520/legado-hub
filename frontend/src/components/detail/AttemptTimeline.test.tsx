import { render, screen } from '@testing-library/react'

import { AttemptTimeline } from './AttemptTimeline'

test('AttemptTimeline keeps attempt order and status labels', () => {
  render(
    <AttemptTimeline
      items={[
        { id: 'a1', label: 'Attempt 1', status: 'failed' },
        { id: 'a2', label: 'Attempt 2', status: 'passed' },
      ]}
    />,
  )

  expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
    'Attempt 1已失败',
    'Attempt 2通过',
  ])
})
