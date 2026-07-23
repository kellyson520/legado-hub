import { DataTable, type DataTableColumn } from '@/components/data/DataTable'
import { MarkdownMessage } from '@/components/ai/MarkdownMessage'

const MAX_CELL_LENGTH = 320
const MAX_COLUMNS = 6

type ToolRecord = Record<string, unknown>

function isRecord(value: unknown): value is ToolRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function displayValue(value: unknown): string {
  if (value == null) return '-'
  if (typeof value === 'string') return value.length > MAX_CELL_LENGTH ? `${value.slice(0, MAX_CELL_LENGTH)}…` : value
  try {
    const serialized = JSON.stringify(value)
    return serialized.length > MAX_CELL_LENGTH ? `${serialized.slice(0, MAX_CELL_LENGTH)}…` : serialized
  } catch {
    return '无法显示'
  }
}

function fallbackJson(value: unknown): string {
  try {
    const serialized = JSON.stringify(value, null, 2)
    return serialized.length > 4000 ? `${serialized.slice(0, 4000)}\n…` : serialized
  } catch {
    return '工具结果无法显示'
  }
}

export function ToolResultRenderer({ value }: { value: unknown }) {
  if (typeof value === 'string') {
    return <MarkdownMessage content={value} className="text-sm" />
  }

  if (Array.isArray(value) && value.length > 0 && value.every(isRecord)) {
    const records = value.map((item, index) => ({ ...item, __row_key: index }))
    const keys = Array.from(new Set(records.flatMap((item) => Object.keys(item).filter((key) => key !== '__row_key')))).slice(0, MAX_COLUMNS)
    const columns: DataTableColumn<ToolRecord & { __row_key: number }>[] = keys.map((key) => ({
      id: key,
      header: key,
      cell: (row) => <span className="block max-w-[18rem] whitespace-pre-wrap break-words text-xs">{displayValue(row[key])}</span>,
    }))
    return <DataTable rows={records} columns={columns} getRowKey={(row) => row.__row_key} emptyLabel="暂无工具结果" />
  }

  if (isRecord(value)) {
    return (
      <dl className="grid gap-2 rounded-md border border-border bg-background/70 p-3 text-xs sm:grid-cols-[minmax(7rem,0.35fr)_minmax(0,1fr)]">
        {Object.entries(value).slice(0, MAX_COLUMNS).map(([key, item]) => (
          <div key={key} className="contents">
            <dt className="rounded bg-muted/50 px-2 py-1 font-semibold text-muted-foreground">{key}</dt>
            <dd className="min-w-0 whitespace-pre-wrap break-words rounded px-2 py-1">{displayValue(item)}</dd>
          </div>
        ))}
      </dl>
    )
  }

  return <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-950 p-3 text-xs leading-5 text-slate-100">{fallbackJson(value)}</pre>
}
