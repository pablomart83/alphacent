import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ColumnDef, RowSelectionState, SortingState } from '@tanstack/react-table'
import { Archive, Download, Trash2 } from 'lucide-react'
import {
  Badge,
  Button,
  Checkbox,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { classifyError, notifyError } from '@/lib/errors'
import { downloadCsv, type CsvColumn } from '@/lib/csv'
import { cn, formatCurrency, formatTimestamp, parseUtcIso } from '@/lib/utils'
import { toast } from 'sonner'
import { useTradingMode } from '@/stores'
import {
  useClosedPositions,
  useDeleteClosedPositions,
  type PositionRow,
} from '../useBookData'

type RangeKey = '1d' | '7d' | '30d' | 'all'
const RANGE_DAYS: Record<RangeKey, number | null> = {
  '1d': 1,
  '7d': 7,
  '30d': 30,
  all: null,
}

function priceForSymbol(v: number | null | undefined, sym: string): string {
  if (v == null) return '—'
  if (/^[A-Z]{6}$/.test(sym.toUpperCase())) return v.toFixed(5)
  if (v < 1) return v.toFixed(6)
  if (v < 10) return v.toFixed(4)
  return v.toFixed(2)
}

export function ClosedPositionsTab() {
  const navigate = useNavigate()
  const mode = useTradingMode((s) => s.mode)
  const [range, setRange] = useState<RangeKey>('30d')
  const [search, setSearch] = useState('')
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'closed_at', desc: true },
  ])
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const [confirmDelete, setConfirmDelete] = useState(false)

  const query = useClosedPositions(undefined, 500)
  const deleteMutation = useDeleteClosedPositions()

  const allRows = query.data?.positions ?? []

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase()
    const days = RANGE_DAYS[range]
    const cutoff = days != null ? Date.now() - days * 86_400_000 : 0
    return allRows.filter((r) => {
      if (days != null && r.closed_at) {
        const t = parseUtcIso(r.closed_at).getTime()
        if (!Number.isNaN(t) && t < cutoff) return false
      }
      if (q) {
        const hit =
          r.symbol.toLowerCase().includes(q) ||
          (r.strategy_name || '').toLowerCase().includes(q) ||
          (r.closure_reason || '').toLowerCase().includes(q)
        if (!hit) return false
      }
      return true
    })
  }, [allRows, range, search])

  const columns = useMemo<ColumnDef<PositionRow>[]>(
    () => [
      {
        id: 'select',
        size: 32,
        header: ({ table }) => (
          <Checkbox
            aria-label="Select all"
            checked={
              table.getIsAllRowsSelected()
                ? true
                : table.getIsSomeRowsSelected()
                  ? 'indeterminate'
                  : false
            }
            onCheckedChange={(v) => table.toggleAllRowsSelected(!!v)}
            onClick={(e) => e.stopPropagation()}
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            aria-label={`Select ${row.original.symbol}`}
            checked={row.getIsSelected()}
            onCheckedChange={(v) => row.toggleSelected(!!v)}
            onClick={(e) => e.stopPropagation()}
          />
        ),
        enableSorting: false,
      },
      {
        id: 'symbol',
        header: 'Symbol',
        accessorKey: 'symbol',
        size: 90,
        cell: ({ row }) => (
          <span className="mono font-semibold text-[var(--text-0)]">{row.original.symbol}</span>
        ),
      },
      {
        id: 'strategy',
        header: 'Strategy',
        accessorKey: 'strategy_name',
        cell: ({ row }) => (
          <span className="truncate max-w-[180px] inline-block align-middle" title={row.original.strategy_name || ''}>
            {row.original.strategy_name || '—'}
          </span>
        ),
      },
      {
        id: 'side',
        header: 'Side',
        size: 60,
        accessorFn: (r) => r.side,
        cell: ({ row }) => {
          const up = (row.original.side || '').toUpperCase()
          const isShort = up.includes('SHORT') || up.includes('SELL')
          return (
            <Badge variant={isShort ? 'error' : 'success'} size="sm">
              {isShort ? 'Short' : 'Long'}
            </Badge>
          )
        },
      },
      {
        id: 'invested',
        header: 'Invested',
        accessorFn: (r) => r.invested_amount ?? r.quantity ?? 0,
        size: 100,
        cell: ({ row }) => (
          <span className="mono tabular-nums">
            {formatCurrency(row.original.invested_amount ?? row.original.quantity ?? 0, { precision: 0 })}
          </span>
        ),
      },
      {
        id: 'entry',
        header: 'Entry',
        accessorKey: 'entry_price',
        size: 96,
        cell: ({ row }) => (
          <span className="mono tabular-nums text-[var(--text-2)]">
            {priceForSymbol(row.original.entry_price, row.original.symbol)}
          </span>
        ),
      },
      {
        id: 'exit',
        header: 'Exit',
        accessorKey: 'current_price',
        size: 96,
        cell: ({ row }) => (
          <span className="mono tabular-nums">
            {priceForSymbol(row.original.current_price, row.original.symbol)}
          </span>
        ),
      },
      {
        id: 'realized_pnl',
        header: 'P&L',
        accessorKey: 'realized_pnl',
        size: 110,
        cell: ({ row }) => (
          <PnLNumber value={row.original.realized_pnl} format="currency" precision={0} size="sm" />
        ),
      },
      {
        id: 'exit_reason',
        header: 'Exit reason',
        accessorKey: 'closure_reason',
        cell: ({ row }) => (
          <span
            className="text-[var(--text-2)] truncate inline-block max-w-[240px] align-middle"
            title={row.original.closure_reason || ''}
          >
            {row.original.closure_reason || '—'}
          </span>
        ),
      },
      {
        id: 'closed_at',
        header: 'Closed',
        accessorFn: (r) => (r.closed_at ? parseUtcIso(r.closed_at).getTime() : 0),
        size: 130,
        cell: ({ row }) => (
          <span className="text-[var(--text-3)] text-[10px]">
            {formatTimestamp(row.original.closed_at, 'short')}
          </span>
        ),
      },
    ],
    [],
  )

  const selectedIds = useMemo(
    () => Object.keys(rowSelection).filter((id) => rowSelection[id]),
    [rowSelection],
  )

  const handleExport = () => {
    const cols: CsvColumn<PositionRow>[] = [
      { header: 'Symbol', value: (r) => r.symbol },
      { header: 'Strategy', value: (r) => r.strategy_name ?? '' },
      { header: 'Side', value: (r) => r.side },
      { header: 'Invested', value: (r) => r.invested_amount ?? r.quantity ?? 0 },
      { header: 'Entry', value: (r) => r.entry_price },
      { header: 'Exit', value: (r) => r.current_price },
      { header: 'Realized PnL', value: (r) => r.realized_pnl },
      { header: 'Exit reason', value: (r) => r.closure_reason ?? '' },
      { header: 'Sector', value: (r) => r.sector ?? '' },
      { header: 'Asset class', value: (r) => r.asset_class ?? '' },
      { header: 'Opened', value: (r) => r.opened_at },
      { header: 'Closed', value: (r) => r.closed_at ?? '' },
    ]
    const now = new Date().toISOString().replace(/[:.]/g, '-')
    downloadCsv(`alphacent-closed-${mode}-${range}-${now}`, rows, cols)
  }

  const handleDelete = async () => {
    if (selectedIds.length === 0) return
    try {
      const res = await deleteMutation.mutateAsync({ positionIds: selectedIds, mode })
      toast.success(`Deleted ${res.deleted} closed position record${res.deleted === 1 ? '' : 's'}`)
      setRowSelection({})
    } catch (e) {
      notifyError(e, 'delete records')
    } finally {
      setConfirmDelete(false)
    }
  }

  if (query.isError) {
    const info = classifyError(query.error, 'closed positions')
    return (
      <ErrorState
        title="Couldn't load closed positions"
        message={info.message}
        onRetry={() => query.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center gap-2 px-2 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Symbol, strategy, reason…"
          className={cn(
            'h-7 px-2 rounded-[3px] bg-[var(--bg-1)] border border-[var(--border-default)] text-[11px] w-[240px]',
            'focus:outline-2 focus:outline-[var(--border-focus)]',
          )}
        />
        <Select value={range} onValueChange={(v) => setRange(v as RangeKey)}>
          <SelectTrigger size="sm" className="h-7 min-w-[100px] text-[11px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1d">Last 24h</SelectItem>
            <SelectItem value="7d">Last 7 days</SelectItem>
            <SelectItem value="30d">Last 30 days</SelectItem>
            <SelectItem value="all">All time</SelectItem>
          </SelectContent>
        </Select>
        <span className="text-[10px] text-[var(--text-3)] mono">
          {rows.length} of {allRows.length}
        </span>
        <div className="ml-auto flex items-center gap-1">
          {selectedIds.length > 0 && (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setConfirmDelete(true)}
              loading={deleteMutation.isPending}
              className="gap-1"
            >
              <Trash2 className="h-3 w-3" />
              Delete {selectedIds.length}
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={handleExport} className="gap-1">
            <Download className="h-3 w-3" />
            CSV
          </Button>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <DataTable<PositionRow>
          data={rows}
          columns={columns}
          rowKey={(r) => r.id}
          loading={query.isLoading}
          sorting={{ state: sorting, onChange: setSorting }}
          selection={{
            mode: 'multi',
            selected: rowSelection,
            onChange: setRowSelection,
          }}
          density="default"
          onRowClick={(r) => navigate(`/book/position/${encodeURIComponent(r.symbol)}`)}
          emptyState={
            <EmptyState
              icon={Archive}
              title={allRows.length === 0 ? 'No closed positions' : 'No matches'}
              description={
                allRows.length === 0
                  ? 'Closed trades will appear here once positions start exiting.'
                  : 'Widen the time range or adjust search.'
              }
            />
          }
        />
      </div>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${selectedIds.length} closed position records`}
        description="This permanently removes the records from the database. Trade-journal history is unaffected. Proceed?"
        confirmLabel="Delete"
        confirmVariant="destructive"
        isLoading={deleteMutation.isPending}
        onConfirm={handleDelete}
      />
    </div>
  )
}
