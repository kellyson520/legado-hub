import { render, screen } from '@testing-library/react'

import { Input } from '@/components/ui/input'
import { FormField } from './FormField'

test('FormField exposes label, help, and error through the control', () => {
  render(
    <FormField label="Name" htmlFor="name" help="Use a display name" error="Required">
      <Input id="name" />
    </FormField>,
  )

  expect(screen.getByLabelText('Name')).toHaveAttribute('aria-describedby', 'name-help name-error')
  expect(screen.getByText('Use a display name')).toHaveAttribute('id', 'name-help')
  expect(screen.getByText('Required')).toHaveAttribute('role', 'alert')
})
