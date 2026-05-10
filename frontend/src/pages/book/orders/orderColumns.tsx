import type { ColumnDef } from '@tanstack/react-table'
import { MoreHorizontal } from 'lucide-react'
import {
  Badge,
  Checkbox,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/primitives'
import { cn, formatCurrency, formatTimestamp, parseUtcIso } from '@/lib/utils'
import type { OrderRow } from '../useBookData'

function priceForSymbol(value: number | null | undefined, symbol: string): string {
  if (value == null) return '—'
  const u = symbol.toUpperCase()
  if (u.length === 6 && /^[A-Z]{6}$/.test(u)) return value.toFixed(5)
  if (value < 1) return value.toFixed(6)
  if (value < 10) return value.toFixed(4)
  return value.toFixed(2)
}

/** Compute slippage in bps: prefer server value when present, else derive
 *  from filled_price vs expected_price, else null.
 *  Backend stores `slippage` as a fraction (e.g. 0.0003 = 3 bps). */
export function slippageBps(row: OrderRow): number | null {
  if (
    row.slippage != null &&
    Number.isFinite(row.slippage) &&
    // Filter sentinel zeros from rows that never actually computed it
    Math.abs(row.slippage) > 0
  ) {
    return row.slippage * 10_000
  }
  if (
    row.filled_price != null &&
    row.expected_price != null &&
    row.expected_price > 0 &&
    row.side
  ) {
    const raw = (row.filled_price - row.expected_price) / row.expected_price
    // SELL slippage is inverted — filling below expected is adverse for LONG,
    // filling above expected is adverse for SHORT. We surface signed bps
    // where positive = adverse cost to the trader.
    const sign = row.side === 'SELL' ? -1 : 1
    return raw * sign * 10_000
  }
  return null
}

function statusVariant(status: OrderRow['status']) {
  switch (status) {
    case 'FILLED':
      return 'success' as const
    case 'PARTIALLY_FILLED':
      return 'info' as const
    case 'PENDING':
    case 'SUBMITTED':
      return 'warning' as const
    case 'CANCELLED':
      return 'muted' as const
    case 'REJECTED':
    case 'FAILED':
      return 'error' as const
    default:
      return 'default' as const
  }
}

export interface OrderColumnActions {
  onCancel: (row: OrderRow) => void
  onDelete: (row: OrderRow) => void
  onClosePosition: (row: OrderRow) => void
  onViewOrder: (row: OrderRow) => void
}

export function buildOrderColumns(actions: OrderColumnActions): ColumnDef<OrderRow>[] {
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
          aria-label={`Select order ${row.original.id}`}
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
        <span
          className="truncate max-w-[180px] inline-block align-middle"
          title={row.original.strategy_name || ''}
        >
          {row.original.strategy_name || '—'}
        </span>
      ),
    },
    {
      id: 'side',
      header: 'Side',
      size: 60,
      accessorFn: (r) => r.side,
      cell: ({ row }) => (
        <Badge variant={row.original.side === 'SELL' ? 'error' : 'success'} size="sm">
          {row.original.side}
        </Badge>
      ),
    },
    {
      id: 'action',
      header: 'Action',
      size: 76,
      accessorKey: 'order_action',
      cell: ({ row }) => {
        const a = row.original.order_action || ''
        const label = a.charAt(0).toUpperCase() + a.slice(1) || '—'
        const variant =
          a === 'entry' ? 'info' : a === 'close' ? 'muted' : a === 'retirement' ? 'warning' : 'default'
        return (
          <Badge variant={variant} size="sm">
            {label}
          </Badge>
        )
      },
    },
    {
      id: 'type',
      header: 'Type',
      size: 80,
      accessorKey: 'order_type',
      cell: ({ row }) => (
        <span className="text-[var(--text-2)] text-[10px] uppercase tracking-wide">
          {row.original.order_type}
        </span>
      ),
    },
    {
      id: 'quantity',
      header: 'Qty',
      accessorKey: 'quantity',
      size: 96,
      cell: ({ row }) => (
        <span className="mono tabular-nums">
          {formatCurrency(row.original.quantity, { precision: 0 })}
        </span>
      ),
    },
    {
      id: 'expected',
      header: 'Expected',
      accessorKey: 'expected_price',
      size: 96,
      cell: ({ row }) => (
        <span className="mono tabular-nums text-[var(--text-2)]">
          {priceForSymbol(row.original.expected_price ?? row.original.price, row.original.symbol)}
        </span>
      ),
    },
    {
      id: 'filled',
      header: 'Filled',
      accessorKey: 'filled_price',
      size: 96,
      cell: ({ row }) => (
        <span className="mono tabular-nums">
          {priceForSymbol(row.original.filled_price, row.original.symbol)}
        </span>
      ),
    },
    {
      id: 'slippage',
      header: 'Slip (bps)',
      accessorFn: (r) => slippageBps(r),
      size: 84,
      cell: ({ getValue }) => {
        const v = getValue<number | null>()
        if (v == null) return <span className="mono text-[var(--text-3)]">—</span>
        const colour =
          Math.abs(v) < 3
            ? 'var(--text-2)'
            : v > 0
              ? 'var(--pnl-down)'
              : 'var(--pnl-up)'
        return (
          <span className="mono tabular-nums" style={{ color: colour }}>
            {v >= 0 ? '+' : ''}
            {v.toFixed(1)}
          </span>
        )
      },
    },
    {
      id: 'fill_time',
      header: 'Fill',
      accessorKey: 'fill_time_seconds',
      size: 70,
      cell: ({ row }) => {
        const v = row.original.fill_time_seconds
        if (v == null) return <span className="mono text-[var(--text-3)]">—</span>
        const colour = v < 5 ? 'var(--pnl-up)' : v < 30 ? 'var(--text-1)' : 'var(--status-warning)'
        const text = v < 60 ? `${v.toFixed(1)}s` : `${Math.round(v / 60)}m`
        return (
          <span className="mono tabular-nums" style={{ color: colour }}>
            {text}
          </span>
        )
      },
    },
    {
      id: 'status',
      header: 'Status',
      size: 110,
      accessorKey: 'status',
      cell: ({ row }) => (
        <Badge variant={statusVariant(row.original.status)} size="sm">
          {row.original.status}
        </Badge>
      ),
    },
    {
      id: 'created',
      header: 'Created',
      accessorFn: (r) => (r.created_at ? parseUtcIso(r.created_at).getTime() : 0),
      size: 130,
      cell: ({ row }) => (
        <span className="text-[var(--text-3)] text-[10px]">
          {formatTimestamp(row.original.created_at, 'short')}
        </span>
      ),
    },
    {
      id: 'actions',
      header: '',
      size: 36,
      enableSorting: false,
      cell: ({ row }) => {
        const r = row.original
        const isPending = r.status === 'PENDING' || r.status === 'SUBMITTED'
        const isTerminal = r.status === 'FILLED' || r.status === 'CANCELLED' || r.status === 'REJECTED' || r.status === 'FAILED'
        return (
          <div
            className="flex items-center justify-end"
            onClick={(e) => e.stopPropagation()}
          >
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label={`Actions for ${r.symbol} order`}
                  className={cn(
                    'h-6 w-6 inline-flex items-center justify-center rounded-[2px]',
                    'text-[var(--text-3)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
                  )}
                >
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => actions.onViewOrder(r)}>
                  View details
                </DropdownMenuItem>
                {r.status === 'FILLED' && r.order_action === 'entry' && (
                  <DropdownMenuItem onSelect={() => actions.onClosePosition(r)}>
                    Close resulting position
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                {isPending && (
                  <DropdownMenuItem
                    onSelect={() => actions.onCancel(r)}
                    className="text-[var(--status-warning)]"
                  >
                    Cancel order
                  </DropdownMenuItem>
                )}
                {isTerminal && (
                  <DropdownMenuItem
                    onSelect={() => actions.onDelete(r)}
                    className="text-[var(--pnl-down)]"
                  >
                    Delete record
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )
      },
    },
  ]
}
