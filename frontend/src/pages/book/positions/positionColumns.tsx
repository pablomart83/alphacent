import type { ColumnDef } from '@tanstack/react-table'
import { MoreHorizontal } from 'lucide-react'
import { Badge, Checkbox, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/primitives'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { cn, formatCurrency, formatTimestamp } from '@/lib/utils'
import type { PositionRow } from '../useBookData'

/* Helper formatters */

function daysHeld(openedAt: string, closedAt?: string | null): number {
  const start = new Date(openedAt.endsWith('Z') ? openedAt : `${openedAt}Z`).getTime()
  const end = closedAt ? new Date(closedAt.endsWith('Z') ? closedAt : `${closedAt}Z`).getTime() : Date.now()
  return Math.max(0, (end - start) / 86_400_000)
}

function holdingColour(days: number): string {
  if (days < 1) return 'var(--text-2)'
  if (days < 7) return 'var(--text-1)'
  if (days < 30) return 'var(--status-warning)'
  return 'var(--pnl-down)'
}

function priceForSymbol(value: number | null | undefined, symbol: string): string {
  if (value == null) return '—'
  // Forex pairs get more precision; very-low-priced (fractional stocks) also.
  const upper = symbol.toUpperCase()
  if (upper.length === 6 && /^[A-Z]{6}$/.test(upper)) {
    return value.toFixed(5)
  }
  if (value < 1) return value.toFixed(6)
  if (value < 10) return value.toFixed(4)
  if (value < 1000) return value.toFixed(2)
  return value.toFixed(2)
}

export interface PositionColumnActions {
  onRowMenuAction: (action: 'detail' | 'modify-risk' | 'close', row: PositionRow) => void
}

export function buildPositionColumns(actions: PositionColumnActions): ColumnDef<PositionRow>[] {
  return [
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
      accessorFn: (row) => row.side,
      size: 60,
      cell: ({ row }) => {
        const upper = (row.original.side || '').toUpperCase()
        const isShort = upper.includes('SHORT') || upper.includes('SELL')
        return (
          <Badge variant={isShort ? 'error' : 'success'} size="sm">
            {isShort ? 'Short' : 'Long'}
          </Badge>
        )
      },
    },
    {
      id: 'status',
      header: 'Status',
      size: 96,
      accessorFn: (row) => (row.pending_closure ? 1 : 0),
      cell: ({ row }) =>
        row.original.pending_closure ? (
          <Badge variant="warning" size="sm">Pending close</Badge>
        ) : (
          <Badge variant="muted" size="sm">Open</Badge>
        ),
    },
    {
      id: 'invested',
      header: 'Invested',
      accessorFn: (row) => row.invested_amount ?? row.quantity ?? 0,
      size: 100,
      cell: ({ row }) => {
        const v = row.original.invested_amount ?? row.original.quantity ?? 0
        return <span className="mono tabular-nums">{formatCurrency(v, { precision: 0 })}</span>
      },
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
      id: 'current',
      header: 'Current',
      accessorKey: 'current_price',
      size: 96,
      cell: ({ row }) => (
        <span className="mono tabular-nums">
          {priceForSymbol(row.original.current_price, row.original.symbol)}
        </span>
      ),
    },
    {
      id: 'pnl',
      header: 'P&L',
      accessorKey: 'unrealized_pnl',
      size: 110,
      cell: ({ row }) => (
        <PnLNumber value={row.original.unrealized_pnl} format="currency" precision={0} size="sm" />
      ),
    },
    {
      id: 'pnl_pct',
      header: '%',
      accessorKey: 'unrealized_pnl_percent',
      size: 80,
      cell: ({ row }) => (
        <PnLNumber value={row.original.unrealized_pnl_percent} format="percentage" precision={2} size="sm" />
      ),
    },
    {
      id: 'sl',
      header: 'SL',
      accessorKey: 'stop_loss',
      size: 96,
      cell: ({ row }) => {
        const sl = row.original.stop_loss
        if (sl == null) return <span className="mono text-[var(--text-3)]">—</span>
        return (
          <span className="mono tabular-nums text-[var(--text-2)]">
            {priceForSymbol(sl, row.original.symbol)}
          </span>
        )
      },
    },
    {
      id: 'tp',
      header: 'TP',
      accessorKey: 'take_profit',
      size: 96,
      cell: ({ row }) => {
        const tp = row.original.take_profit
        if (tp == null) return <span className="mono text-[var(--text-3)]">—</span>
        return (
          <span className="mono tabular-nums text-[var(--text-2)]">
            {priceForSymbol(tp, row.original.symbol)}
          </span>
        )
      },
    },
    {
      id: 'holding',
      header: 'Held',
      accessorFn: (row) => daysHeld(row.opened_at, row.closed_at),
      size: 70,
      cell: ({ row }) => {
        const d = daysHeld(row.original.opened_at, row.original.closed_at)
        const text = d < 1 ? `${Math.round(d * 24)}h` : `${d.toFixed(d < 10 ? 1 : 0)}d`
        return (
          <span
            className="mono tabular-nums"
            style={{ color: holdingColour(d) }}
            title={formatTimestamp(row.original.opened_at)}
          >
            {text}
          </span>
        )
      },
    },
    {
      id: 'opened',
      header: 'Opened',
      accessorKey: 'opened_at',
      size: 130,
      cell: ({ row }) => (
        <span className="text-[var(--text-3)] text-[10px]">
          {formatTimestamp(row.original.opened_at, 'short')}
        </span>
      ),
    },
    {
      id: 'actions',
      header: '',
      size: 36,
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex items-center justify-end" onClick={(e) => e.stopPropagation()}>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label={`Actions for ${row.original.symbol}`}
                className={cn(
                  'h-6 w-6 inline-flex items-center justify-center rounded-[2px]',
                  'text-[var(--text-3)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
                )}
              >
                <MoreHorizontal className="h-3.5 w-3.5" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => actions.onRowMenuAction('detail', row.original)}>
                View detail
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => actions.onRowMenuAction('modify-risk', row.original)}>
                Modify SL/TP
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => actions.onRowMenuAction('close', row.original)}
                className="text-[var(--pnl-down)]"
              >
                Close position
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
    },
  ]
}
