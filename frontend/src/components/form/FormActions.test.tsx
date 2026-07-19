import { render, screen } from '@testing-library/react'

import { Button } from '@/components/ui/button'
import { FormActions } from './FormActions'

test('FormActions groups submit controls in one action region', () => {
  render(
    <FormActions>
      <Button type="submit">Save</Button>
    </FormActions>,
  )

  expect(screen.getByRole('button', { name: 'Save' }).parentElement).toHaveClass('justify-end')
})
