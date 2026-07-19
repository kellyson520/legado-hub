import { render, screen } from '@testing-library/react'

import { DataTable } from './DataTable'

test('DataTable renders typed columns and table headers', () => {
  render(
    <DataTable
      rows={[{ id: 'run-1', name: 'source_build' }]}
      getRowKey={(row) => row.id}
      columns={[
        { id: 'name', header: '运行', cell: (row) => row.name },
      ]}
    />,
  )

  expect(screen.getByRole('columnheader', { name: '运行' })).toBeInTheDocument()
  expect(screen.getByRole('cell', { name: 'source_build' })).toBeInTheDocument()
})

test('DataTable renders an accessible empty state without a fake row', () => {
  render(
    <DataTable
      rows={[]}
      columns={[{ id: 'name', header: 'Name', cell: () => null }]}
      getRowKey={() => 'empty'}
      emptyLabel="No rows"
    />,
  )

  expect(screen.getByText('No rows')).toBeInTheDocument()
  expect(screen.getAllByRole('row')).toHaveLength(2)
})
