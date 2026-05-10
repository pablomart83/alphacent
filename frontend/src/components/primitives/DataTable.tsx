import { useRef, type ReactNode } from 'react'
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type OnChangeFn,
  type Row,
  type RowSelectionState,
  type SortingState,
  type Table as TableInstance,
} from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Skeleton } from './Skeleton'

export interface DataTableProps<TData extends object> {
  data: TData[]
  columns: ColumnDef<TData, any>[]
  rowKey: (row: TData, index: number) => string

  /** Force virtualization on/off. Defaults to auto-on when data.length > 100. */
  virtualized?: boolean
  estimatedRowHeight?: number

  /** Row selection (only when mode: "multi") — keyed by `rowKey(row)`. */
  selection?: {
    mode: 'single' | 'multi'
    selected: RowSelectionState
    onChange: OnChangeFn<RowSelectionState>
  }

  sorting?: {
    state: SortingState
    onChange: OnChangeFn<SortingState>
  }

  density?: 'compact' | 'default' | 'comfortable'
  onRowClick?: (row: TData) => void
  /** Key of the currently-highlighted row — drives the `selected` left-border. */
  activeRowId?: string | null

  loading?: boolean
  emptyState?: ReactNode

  /** Called when the user scrolls near the bottom; use to page-in closed rows. */
  loadMore?: () => void
  hasMore?: boolean
  loadMoreThresholdPx?: number

  className?: string
  bodyClassName?: string

  /** Exposes the TanStack Table instance — use for imperative operations. */
  onReady?: (table: TableInstance<TData>) => void
}

const DENSITY_ROW_H = { compact: 24, default: 28, comfortable: 36 } as const
const DENSITY_TEXT = {
  compact: 'text-[10px]',
  default: 'text-[11px]',
  comfortable: 'text-[12px]',
} as const

export function DataTable<TData extends object>({
  data,
  columns,
  rowKey,
  virtualized,
  estimatedRowHeight,
  selection,
  sorting,
  density = 'default',
  onRowClick,
  activeRowId,
  loading = false,
  emptyState,
  loadMore,
  hasMore,
  loadMoreThresholdPx = 400,
  className,
  bodyClassName,
  onReady,
}: DataTableProps<TData>) {
  const shouldVirtualize = virtualized ?? data.length > 100
  const rowHeight = estimatedRowHeight ?? DENSITY_ROW_H[density]

  const table = useReactTable({
    data,
    columns,
    getRowId: (row, index) => rowKey(row, index),
    state: {
      sorting: sorting?.state,
      // TanStack Table indexes into `rowSelection` unconditionally inside
      // `row.getIsSelected()`. Omitting it raises a TypeError on every row.
      // Keep an empty dict when the caller doesn't wire selection.
      rowSelection: selection?.selected ?? {},
    },
    onSortingChange: sorting?.onChange,
    onRowSelectionChange: selection?.onChange,
    enableRowSelection: !!selection,
    enableMultiRowSelection: selection?.mode === 'multi',
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (onReady) {
    // Idempotent — TanStack returns the same instance unless deps change.
    onReady(table)
  }

  const containerRef = useRef<HTMLDivElement>(null)
  const rowsModel = table.getRowModel()
  const rows = rowsModel.rows

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => rowHeight,
    overscan: 12,
    enabled: shouldVirtualize,
  })

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    if (!loadMore || !hasMore) return
    const el = e.currentTarget
    if (el.scrollHeight - el.scrollTop - el.clientHeight < loadMoreThresholdPx) {
      loadMore()
    }
  }

  const colCount = table.getAllLeafColumns().length

  const body = (() => {
    if (loading && rows.length === 0) {
      return (
        <tbody>
          {Array.from({ length: 8 }).map((_, i) => (
            <tr key={i}>
              <td colSpan={colCount} className="px-2 py-1">
                <Skeleton variant="table-row" />
              </td>
            </tr>
          ))}
        </tbody>
      )
    }

    if (rows.length === 0) {
      return (
        <tbody>
          <tr>
            <td colSpan={colCount} className="p-0">
              {emptyState}
            </td>
          </tr>
        </tbody>
      )
    }

    if (!shouldVirtualize) {
      return (
        <tbody>
          {rows.map((row) => (
            <DataTableRow
              key={row.id}
              row={row}
              rowHeight={rowHeight}
              density={density}
              active={activeRowId === row.id}
              onRowClick={onRowClick}
            />
          ))}
        </tbody>
      )
    }

    // Virtualized body — uses absolute-positioned rows.
    const virtualRows = virtualizer.getVirtualItems()
    const totalHeight = virtualizer.getTotalSize()
    const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0
    const paddingBottom =
      virtualRows.length > 0 ? totalHeight - virtualRows[virtualRows.length - 1].end : 0

    return (
      <tbody>
        {paddingTop > 0 && (
          <tr>
            <td colSpan={colCount} style={{ height: paddingTop }} />
          </tr>
        )}
        {virtualRows.map((vr) => {
          const row = rows[vr.index]
          return (
            <DataTableRow
              key={row.id}
              row={row}
              rowHeight={rowHeight}
              density={density}
              active={activeRowId === row.id}
              onRowClick={onRowClick}
            />
          )
        })}
        {paddingBottom > 0 && (
          <tr>
            <td colSpan={colCount} style={{ height: paddingBottom }} />
          </tr>
        )}
      </tbody>
    )
  })()

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className={cn(
        'relative h-full min-h-0 overflow-auto bg-[var(--bg-1)]',
        DENSITY_TEXT[density],
        className,
      )}
    >
      <table className={cn('w-full border-collapse', bodyClassName)}>
        <thead className="sticky top-0 z-10 bg-[var(--bg-1)]">
          {table.getHeaderGroups().map((headerGroup) => (
            <tr
              key={headerGroup.id}
              className="border-b border-[var(--border-default)] bg-[var(--bg-1)]"
            >
              {headerGroup.headers.map((header) => {
                const canSort = header.column.getCanSort()
                const sortDir = header.column.getIsSorted()
                return (
                  <th
                    key={header.id}
                    className={cn(
                      'text-left font-medium text-[10px] uppercase tracking-wider',
                      'text-[var(--text-3)] px-2 py-1 whitespace-nowrap select-none',
                      canSort && 'cursor-pointer hover:text-[var(--text-1)]',
                    )}
                    style={{ width: header.column.columnDef.size }}
                    onClick={
                      canSort
                        ? (e) => header.column.toggleSorting(undefined, e.shiftKey)
                        : undefined
                    }
                  >
                    <span className="inline-flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {canSort && (
                        <SortIndicator dir={sortDir === 'asc' ? 'asc' : sortDir === 'desc' ? 'desc' : null} />
                      )}
                    </span>
                  </th>
                )
              })}
            </tr>
          ))}
        </thead>
        {body}
      </table>
      {hasMore && rows.length > 0 && (
        <div className="py-2 text-center text-[10px] text-[var(--text-3)]">
          Scroll for more…
        </div>
      )}
    </div>
  )
}

function SortIndicator({ dir }: { dir: 'asc' | 'desc' | null }) {
  if (dir === 'asc') return <ArrowUp className="h-3 w-3 text-[var(--text-1)]" />
  if (dir === 'desc') return <ArrowDown className="h-3 w-3 text-[var(--text-1)]" />
  return <ChevronsUpDown className="h-3 w-3 opacity-50" />
}

function DataTableRow<TData extends object>({
  row,
  rowHeight,
  density,
  active,
  onRowClick,
}: {
  row: Row<TData>
  rowHeight: number
  density: 'compact' | 'default' | 'comfortable'
  active?: boolean
  onRowClick?: (row: TData) => void
}) {
  const selected = row.getIsSelected()
  const cellPad =
    density === 'compact' ? 'px-2 py-0.5' : density === 'comfortable' ? 'px-2 py-1.5' : 'px-2 py-1'
  return (
    <tr
      onClick={onRowClick ? () => onRowClick(row.original) : undefined}
      className={cn(
        'border-b border-[var(--border-subtle)] transition-colors',
        onRowClick && 'cursor-pointer',
        selected
          ? 'bg-[color-mix(in_oklab,var(--accent-primary)_10%,transparent)]'
          : active
            ? 'bg-[var(--bg-active)]'
            : 'hover:bg-[var(--bg-hover)]',
      )}
      style={{ height: rowHeight }}
      data-row-id={row.id}
    >
      {row.getVisibleCells().map((cell) => (
        <td
          key={cell.id}
          className={cn(cellPad, 'whitespace-nowrap text-[var(--text-1)] align-middle')}
          style={{ width: cell.column.columnDef.size }}
        >
          {flexRender(cell.column.columnDef.cell, cell.getContext())}
        </td>
      ))}
    </tr>
  )
}
