import React, { memo, useRef } from 'react';
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
  type ColumnFiltersState,
  type RowSelectionState,
  type OnChangeFn,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronDown, ChevronUp, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  pageSize?: number;
  showPagination?: boolean;
  className?: string;
  rowSelection?: RowSelectionState;
  onRowSelectionChange?: OnChangeFn<RowSelectionState>;
  getRowId?: (row: TData) => string;
  /**
   * When true, renders all rows via virtual scrolling instead of pagination.
   * Only the visible rows are in the DOM — the rest are rendered as empty space.
   * Use for tables with 100+ rows (closed positions, orders, trade journal).
   * The container must have a fixed height (set via className, e.g. "h-[600px]").
   * Default: false (uses pagination).
   */
  virtualise?: boolean;
  /** Row height estimate for the virtualiser (default: 36px). */
  estimatedRowHeight?: number;
  /** Called when a row is clicked. Useful for opening detail dialogs. */
  onRowClick?: (row: TData) => void;
}

// ── Shared header renderer ────────────────────────────────────────────────

function TableHeader<TData, TValue>({
  table,
  columns,
}: {
  table: ReturnType<typeof useReactTable<TData>>;
  columns: ColumnDef<TData, TValue>[];
}) {
  return (
    <thead className="sticky top-0 z-10 bg-dark-bg">
      {table.getHeaderGroups().map((headerGroup) => (
        <tr key={headerGroup.id} className="border-b border-dark-border">
          {headerGroup.headers.map((header) => (
            <th
              key={header.id}
              className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
            >
              {header.isPlaceholder ? null : (
                <div
                  className={cn(
                    'flex items-center gap-1',
                    header.column.getCanSort() && 'cursor-pointer select-none'
                  )}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  {flexRender(header.column.columnDef.header, header.getContext())}
                  {header.column.getCanSort() && (
                    <span>
                      {header.column.getIsSorted() === 'asc' ? (
                        <ChevronUp className="h-3 w-3 text-accent-green" />
                      ) : header.column.getIsSorted() === 'desc' ? (
                        <ChevronDown className="h-3 w-3 text-accent-green" />
                      ) : (
                        <ChevronsUpDown className="h-3 w-3 opacity-30" />
                      )}
                    </span>
                  )}
                </div>
              )}
            </th>
          ))}
        </tr>
      ))}
    </thead>
  );
}

// ── Main component ────────────────────────────────────────────────────────

function DataTableComponent<TData, TValue>({
  columns,
  data,
  pageSize = 10,
  showPagination = true,
  className,
  rowSelection,
  onRowSelectionChange,
  getRowId,
  virtualise = false,
  estimatedRowHeight = 36,
  onRowClick,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [internalRowSelection, setInternalRowSelection] = React.useState<RowSelectionState>({});

  const currentRowSelection = rowSelection !== undefined ? rowSelection : internalRowSelection;
  const handleRowSelectionChange = onRowSelectionChange || setInternalRowSelection;

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    // Only register pagination model when not virtualising
    ...(virtualise ? {} : { getPaginationRowModel: getPaginationRowModel() }),
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onRowSelectionChange: handleRowSelectionChange,
    getRowId,
    state: {
      sorting,
      columnFilters,
      rowSelection: currentRowSelection,
    },
    initialState: {
      pagination: { pageSize },
    },
    enableRowSelection: true,
    // When virtualising, show all rows (no pagination model active)
    ...(virtualise ? { manualPagination: false } : {}),
  });

  // ── Virtual scrolling path ──────────────────────────────────────────────
  const scrollRef = useRef<HTMLDivElement>(null);

  // All rows (sorted + filtered) for the virtualiser
  const allRows = virtualise ? table.getRowModel().rows : [];

  const virtualiser = useVirtualizer({
    count: allRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => estimatedRowHeight,
    overscan: 15,
  });

  if (virtualise) {
    const virtualItems = virtualiser.getVirtualItems();
    const totalHeight = virtualiser.getTotalSize();

    // Column widths — use the column size if defined, otherwise distribute evenly.
    // table-layout: fixed + explicit col widths ensures header and body align.
    const colWidths = table.getAllColumns().map(col => col.getSize() || 0);
    const hasExplicitWidths = colWidths.some(w => w > 0);

    return (
      <div className={cn('flex flex-col', className)}>
        <div
          ref={scrollRef}
          className="overflow-auto rounded-md border border-border flex-1"
        >
          <table
            className="w-full text-xs"
            style={{ tableLayout: hasExplicitWidths ? 'fixed' : 'auto', minWidth: '100%' }}
          >
            {hasExplicitWidths && (
              <colgroup>
                {colWidths.map((w, i) => (
                  <col key={i} style={{ width: w > 0 ? `${w}px` : undefined }} />
                ))}
              </colgroup>
            )}
            <TableHeader table={table} columns={columns} />
            <tbody>
              {/* Spacer row for virtual offset top */}
              {virtualItems.length > 0 && virtualItems[0].start > 0 && (
                <tr style={{ height: `${virtualItems[0].start}px` }} />
              )}
              {virtualItems.map((virtualRow) => {
                const row = allRows[virtualRow.index];
                return (
                  <tr
                    key={row.id}
                    data-index={virtualRow.index}
                    ref={virtualiser.measureElement}
                    className={cn(
                      'border-b border-dark-border/50 hover:bg-dark-surface/50 transition-colors even:bg-[rgba(31,41,55,0.5)]',
                      onRowClick && 'cursor-pointer'
                    )}
                    onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-1.5 overflow-hidden text-ellipsis">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                );
              })}
              {/* Spacer row for virtual offset bottom */}
              {virtualItems.length > 0 && (() => {
                const lastItem = virtualItems[virtualItems.length - 1];
                const remaining = totalHeight - lastItem.end;
                return remaining > 0 ? <tr style={{ height: `${remaining}px` }} /> : null;
              })()}
            </tbody>
          </table>
          {allRows.length === 0 && (
            <div className="px-3 py-8 text-center text-gray-500 text-xs">
              No results found.
            </div>
          )}
        </div>
        <div className="px-1 pt-1 text-xs text-gray-500 font-mono">
          {allRows.length.toLocaleString()} row{allRows.length !== 1 ? 's' : ''}
        </div>
      </div>
    );
  }

  // ── Paginated path (unchanged behaviour) ───────────────────────────────
  return (
    <div className={cn('space-y-4', className)}>
      <div className="rounded-md border border-border overflow-x-auto">
        <table className="w-full text-xs">
          <TableHeader table={table} columns={columns} />
          <tbody>
            {table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className={cn(
                    'border-b border-dark-border/50 hover:bg-dark-surface/50 transition-colors even:bg-[rgba(31,41,55,0.5)]',
                    onRowClick && 'cursor-pointer'
                  )}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={columns.length} className="px-3 py-8 text-center text-gray-500">
                  No results found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showPagination && table.getPageCount() > 1 && (
        <div className="flex items-center justify-between px-1">
          <div className="text-xs text-gray-500 font-mono">
            {table.getState().pagination.pageIndex * pageSize + 1}–{Math.min(
              (table.getState().pagination.pageIndex + 1) * pageSize,
              data.length
            )} of {data.length.toLocaleString()}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              className="h-7 text-xs"
            >
              Prev
            </Button>
            <div className="text-xs text-gray-500 font-mono">
              {table.getState().pagination.pageIndex + 1}/{table.getPageCount()}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              className="h-7 text-xs"
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export const DataTable = memo(DataTableComponent) as typeof DataTableComponent;
