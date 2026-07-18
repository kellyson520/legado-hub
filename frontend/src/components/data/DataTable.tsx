import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

export interface DataTableColumn<Row> {
  id: string
  header: ReactNode
  cell: (row: Row) => ReactNode
  className?: string
}

export interface DataTableProps<Row> {
  rows: Row[]
  columns: DataTableColumn<Row>[]
  getRowKey: (row: Row) => string | number
  className?: string
}

export function DataTable<Row>({ rows, columns, getRowKey, className }: DataTableProps<Row>) {
  return (
    <div className={cn('overflow-hidden rounded-md border border-border bg-card', className)}>
      <Table>
        <TableHeader className="bg-muted/40">
          <TableRow className="hover:bg-transparent">
            {columns.map((column) => <TableHead key={column.id} className={column.className}>{column.header}</TableHead>)}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={getRowKey(row)}>
              {columns.map((column) => <TableCell key={column.id} className={column.className}>{column.cell(row)}</TableCell>)}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
