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
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/primitives'
import { ConvictionBar } from '@/components/trading/ConvictionBar'
import { RegimePill } from '@/components/trading/RegimePill'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { cn, formatCurrency, formatPercentage, formatTimestamp } from '@/lib/utils'
import type { StrategyRow, StrategyStatus } from '../useStrategiesData'

/* ─────────────────────────── formatters ─────────────────────────── */

const STATUS_VARIANT: Record<string, 'paper' | 'backtested' | 'live' | 'retired' | 'info' | 'muted'> = {
  PROPOSED: 'info',
  BACKTESTED: 'backtested',
  PAPER: 'paper',
  DEMO: 'paper',
  LIVE: 'live',
  RETIRED: 'retired',
}

function statusLabel(status: StrategyStatus): string {
  // DEMO is legacy naming — display as PAPER in the UI.
  return status === 'DEMO' ? 'PAPER' : status
}

const CATEGORY_VARIANT: Record<string, 'info' | 'success' | 'muted'> = {
  alpha_edge: 'success',
  template_based: 'info',
  manual: 'muted',
  statistical: 'info',
}

function categoryLabel(cat?: string | null): string {
  if (!cat) return 'manual'
  return cat.replace(/_/g, ' ')
}

function healthDot(score: number | null | undefined): { color: string; label: string } {
  if (score == null) return { color: 'var(--text-3)', label: '—' }
  if (score >= 4) return { color: 'var(--pnl-up)', label: String(score) }
  if (score >= 3) return { color: 'var(--accent-primary)', label: String(score) }
  if (score >= 2) return { color: 'var(--status-warning)', label: String(score) }
  return { color: 'var(--pnl-down)', label: String(score) }
}

function decayColor(score: number | null | undefined): string {
  if (score == null) return 'var(--text-3)'
  if (score >= 7) return 'var(--pnl-up)'
  if (score >= 4) return 'var(--status-warning)'
  return 'var(--pnl-down)'
}

export interface StrategyColumnActions {
  onRowMenuAction: (
    action:
      | 'detail'
      | 'activate'
      | 'deactivate'
      | 'backtest'
      | 'retire'
      | 'delete-permanent',
    row: StrategyRow,
  ) => void
}

/* ─────────────────────────── columns ─────────────────────────── */

export function buildStrategyColumns(
  actions: StrategyColumnActions,
): ColumnDef<StrategyRow>[] {
  return [
    {
      id: 'select',
      size: 32,
      enableSorting: false,
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
          aria-label={`Select ${row.original.name}`}
          checked={row.getIsSelected()}
          onCheckedChange={(v) => row.toggleSelected(!!v)}
          onClick={(e) => e.stopPropagation()}
        />
      ),
    },
    {
      id: 'name',
      header: 'Strategy',
      accessorKey: 'name',
      size: 260,
      cell: ({ row }) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            actions.onRowMenuAction('detail', row.original)
          }}
          className="text-left font-medium text-[var(--text-0)] hover:text-[var(--accent-primary)] truncate max-w-[240px] block"
          title={row.original.name}
        >
          {row.original.name}
        </button>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      accessorKey: 'status',
      size: 110,
      cell: ({ row }) => {
        const status = row.original.status
        const variant = STATUS_VARIANT[status] ?? 'muted'
        const isLive = row.original.is_live_authorized
        return (
          <div className="flex items-center gap-1">
            <Badge variant={variant} size="sm">
              {statusLabel(status)}
            </Badge>
            {isLive && (
              <Badge variant="live" size="sm" className="gap-0.5">
                <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
                LIVE
              </Badge>
            )}
          </div>
        )
      },
    },
    {
      id: 'category',
      header: 'Category',
      accessorFn: (row) => row.strategy_category ?? 'manual',
      size: 110,
      cell: ({ row }) => {
        const cat = row.original.strategy_category ?? 'manual'
        const variant = CATEGORY_VARIANT[cat] ?? 'muted'
        return (
          <Badge variant={variant} size="sm">
            {categoryLabel(cat)}
          </Badge>
        )
      },
    },
    {
      id: 'template',
      header: 'Template',
      accessorFn: (row) => row.template_name ?? row.metadata?.template_name ?? '',
      size: 170,
      cell: ({ row }) => {
        const t = row.original.template_name ?? row.original.metadata?.template_name ?? '—'
        return (
          <span
            className="truncate max-w-[160px] inline-block align-middle text-[var(--text-2)]"
            title={t}
          >
            {t}
          </span>
        )
      },
    },
    {
      id: 'regime',
      header: 'Regime',
      accessorFn: (row) =>
        row.market_regime ?? row.metadata?.market_regime ?? row.metadata?.activation_regime ?? '',
      size: 140,
      cell: ({ row }) => {
        const regime =
          row.original.market_regime ??
          row.original.metadata?.market_regime ??
          row.original.metadata?.activation_regime ??
          null
        if (!regime) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return <RegimePill regime={regime} size="sm" showConfidence={false} />
      },
    },
    {
      id: 'symbols',
      header: 'Symbols',
      accessorFn: (row) => row.symbols?.length ?? 0,
      size: 80,
      cell: ({ row }) => {
        const symbols = row.original.symbols ?? []
        const traded = row.original.traded_symbols ?? []
        if (symbols.length === 0)
          return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                onClick={(e) => e.stopPropagation()}
                className="mono tabular-nums text-[var(--text-1)] hover:text-[var(--accent-primary)]"
                title={`${symbols.length} symbols`}
              >
                {symbols.length}
                {traded.length > 0 && (
                  <span className="text-[var(--text-3)] ml-0.5">
                    ({traded.length}●)
                  </span>
                )}
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="max-w-[320px]">
              <div className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-3)] mb-1">
                Watchlist ({symbols.length})
              </div>
              <div className="flex flex-wrap gap-1 mb-2">
                {symbols.map((s) => {
                  const isTraded = traded.includes(s)
                  return (
                    <span
                      key={s}
                      className={cn(
                        'inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-[2px] mono text-[10px]',
                        isTraded
                          ? 'bg-[color-mix(in_oklab,var(--pnl-up)_12%,transparent)] text-[var(--pnl-up)]'
                          : 'bg-[var(--bg-2)] text-[var(--text-1)]',
                      )}
                    >
                      {isTraded && <span className="h-1 w-1 rounded-full bg-current" />}
                      {s}
                    </span>
                  )
                })}
              </div>
              {traded.length > 0 && (
                <div className="text-[10px] text-[var(--text-3)]">
                  <span className="mono text-[var(--pnl-up)]">●</span> = has open position
                </div>
              )}
            </PopoverContent>
          </Popover>
        )
      },
    },
    {
      id: 'allocation_percent',
      header: 'Alloc %',
      accessorKey: 'allocation_percent',
      size: 80,
      cell: ({ row }) => {
        const v = row.original.allocation_percent ?? 0
        if (!v) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span className="mono tabular-nums text-[var(--text-1)]">
            {v.toFixed(1)}%
          </span>
        )
      },
    },
    {
      id: 'sharpe',
      header: 'Sharpe',
      accessorFn: (row) => row.performance_metrics?.sharpe_ratio ?? null,
      size: 72,
      cell: ({ row }) => {
        const s = row.original.performance_metrics?.sharpe_ratio
        if (s == null || !Number.isFinite(s))
          return <span className="text-[var(--text-3)] text-[10px]">—</span>
        const color =
          s >= 1.5
            ? 'var(--pnl-up)'
            : s >= 1.0
              ? 'var(--text-1)'
              : s >= 0.5
                ? 'var(--status-warning)'
                : 'var(--pnl-down)'
        return (
          <span className="mono tabular-nums" style={{ color }}>
            {s.toFixed(2)}
          </span>
        )
      },
    },
    {
      id: 'total_return',
      header: 'Return',
      accessorFn: (row) => row.performance_metrics?.total_return ?? null,
      size: 80,
      cell: ({ row }) => {
        const v = row.original.performance_metrics?.total_return
        if (v == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <PnLNumber
            value={v * 100}
            format="percentage"
            precision={1}
            size="sm"
            showSign
          />
        )
      },
    },
    {
      id: 'max_drawdown',
      header: 'Max DD',
      accessorFn: (row) => row.performance_metrics?.max_drawdown ?? null,
      size: 80,
      cell: ({ row }) => {
        const dd = row.original.performance_metrics?.max_drawdown
        if (dd == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span className="mono tabular-nums text-[var(--pnl-down)]">
            {(dd * 100).toFixed(1)}%
          </span>
        )
      },
    },
    {
      id: 'win_rate',
      header: 'Win %',
      accessorFn: (row) => row.performance_metrics?.win_rate ?? null,
      size: 72,
      cell: ({ row }) => {
        const wr = row.original.performance_metrics?.win_rate
        if (wr == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span className="mono tabular-nums text-[var(--text-1)]">
            {(wr * 100).toFixed(0)}%
          </span>
        )
      },
    },
    {
      id: 'trades',
      header: 'Trades',
      accessorFn: (row) => row.performance_metrics?.total_trades ?? 0,
      size: 70,
      cell: ({ row }) => (
        <span className="mono tabular-nums text-[var(--text-1)]">
          {row.original.performance_metrics?.total_trades ?? 0}
        </span>
      ),
    },
    {
      id: 'open_positions',
      header: 'Open',
      accessorFn: (row) => row.performance_metrics?.open_positions ?? 0,
      size: 64,
      cell: ({ row }) => {
        const n = row.original.performance_metrics?.open_positions ?? 0
        if (n === 0) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span className="mono tabular-nums text-[var(--text-0)] font-medium">{n}</span>
        )
      },
    },
    {
      id: 'conviction',
      header: 'Conviction',
      accessorFn: (row) => row.metadata?.conviction_score ?? null,
      size: 120,
      cell: ({ row }) => {
        const score = row.original.metadata?.conviction_score
        if (score == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return <ConvictionBar score={score} size="mini" showValue />
      },
    },
    {
      id: 'health',
      header: 'Health',
      accessorFn: (row) =>
        row.performance_metrics?.health_score ?? row.metadata?.health_score ?? null,
      size: 64,
      cell: ({ row }) => {
        const score =
          row.original.performance_metrics?.health_score ??
          row.original.metadata?.health_score ??
          null
        const { color, label } = healthDot(score)
        return (
          <span className="inline-flex items-center gap-1">
            <span
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="mono tabular-nums text-[var(--text-1)]">{label}</span>
          </span>
        )
      },
    },
    {
      id: 'decay',
      header: 'Decay',
      accessorFn: (row) =>
        row.performance_metrics?.decay_score ?? row.metadata?.decay_score ?? null,
      size: 64,
      cell: ({ row }) => {
        const d =
          row.original.performance_metrics?.decay_score ??
          row.original.metadata?.decay_score ??
          null
        if (d == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span className="mono tabular-nums" style={{ color: decayColor(d) }}>
            {d}/10
          </span>
        )
      },
    },
    {
      id: 'alpha_vs_spy',
      header: 'vs SPY',
      accessorFn: (row) => row.alpha_vs_spy ?? null,
      size: 80,
      cell: ({ row }) => {
        const a = row.original.alpha_vs_spy
        if (a == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return <PnLNumber value={a * 100} format="percentage" precision={1} size="sm" showSign />
      },
    },
    {
      id: 'last_activated',
      header: 'Activated',
      accessorKey: 'activated_at',
      size: 116,
      cell: ({ row }) => (
        <span className="text-[var(--text-3)] text-[10px]">
          {formatTimestamp(row.original.activated_at, 'short')}
        </span>
      ),
    },
    {
      id: 'actions',
      header: '',
      size: 36,
      enableSorting: false,
      cell: ({ row }) => {
        const s = row.original
        const status = s.status
        return (
          <div className="flex items-center justify-end" onClick={(e) => e.stopPropagation()}>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label={`Actions for ${s.name}`}
                  className="h-6 w-6 inline-flex items-center justify-center rounded-[2px] text-[var(--text-3)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]"
                >
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={() => actions.onRowMenuAction('detail', s)}
                >
                  View detail
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                {status === 'BACKTESTED' && (
                  <DropdownMenuItem
                    onSelect={() => actions.onRowMenuAction('activate', s)}
                  >
                    Activate
                  </DropdownMenuItem>
                )}
                {(status === 'PAPER' || status === 'LIVE' || status === 'DEMO') && (
                  <DropdownMenuItem
                    onSelect={() => actions.onRowMenuAction('deactivate', s)}
                  >
                    Deactivate
                  </DropdownMenuItem>
                )}
                {status === 'PROPOSED' && (
                  <DropdownMenuItem
                    onSelect={() => actions.onRowMenuAction('backtest', s)}
                  >
                    Run backtest
                  </DropdownMenuItem>
                )}
                {status !== 'RETIRED' && (
                  <DropdownMenuItem
                    onSelect={() => actions.onRowMenuAction('retire', s)}
                    className="text-[var(--pnl-down)]"
                  >
                    Retire
                  </DropdownMenuItem>
                )}
                {status === 'RETIRED' && (
                  <DropdownMenuItem
                    onSelect={() => actions.onRowMenuAction('delete-permanent', s)}
                    className="text-[var(--pnl-down)]"
                  >
                    Permanently delete
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

/* ─────────────── CSV export column spec (shared) ─────────────── */
export const strategyCsvColumns = [
  { header: 'Name', value: (r: StrategyRow) => r.name },
  { header: 'Status', value: (r: StrategyRow) => statusLabel(r.status) },
  { header: 'Category', value: (r: StrategyRow) => r.strategy_category ?? 'manual' },
  {
    header: 'Template',
    value: (r: StrategyRow) => r.template_name ?? r.metadata?.template_name ?? '',
  },
  {
    header: 'Regime',
    value: (r: StrategyRow) =>
      r.market_regime ?? r.metadata?.market_regime ?? '',
  },
  { header: 'Symbols', value: (r: StrategyRow) => (r.symbols ?? []).join('|') },
  { header: 'Allocation', value: (r: StrategyRow) => r.allocation_percent ?? 0 },
  {
    header: 'Sharpe',
    value: (r: StrategyRow) => r.performance_metrics?.sharpe_ratio ?? '',
  },
  {
    header: 'Return',
    value: (r: StrategyRow) => r.performance_metrics?.total_return ?? '',
  },
  {
    header: 'Max DD',
    value: (r: StrategyRow) => r.performance_metrics?.max_drawdown ?? '',
  },
  {
    header: 'Win rate',
    value: (r: StrategyRow) => r.performance_metrics?.win_rate ?? '',
  },
  { header: 'Trades', value: (r: StrategyRow) => r.performance_metrics?.total_trades ?? 0 },
  {
    header: 'Open positions',
    value: (r: StrategyRow) => r.performance_metrics?.open_positions ?? 0,
  },
  { header: 'Conviction', value: (r: StrategyRow) => r.metadata?.conviction_score ?? '' },
  {
    header: 'Health',
    value: (r: StrategyRow) =>
      r.performance_metrics?.health_score ?? r.metadata?.health_score ?? '',
  },
  {
    header: 'Decay',
    value: (r: StrategyRow) =>
      r.performance_metrics?.decay_score ?? r.metadata?.decay_score ?? '',
  },
  { header: 'Alpha vs SPY', value: (r: StrategyRow) => r.alpha_vs_spy ?? '' },
  { header: 'Activated', value: (r: StrategyRow) => r.activated_at ?? '' },
  { header: 'Created', value: (r: StrategyRow) => r.created_at ?? '' },
]

// Silence unused — helpers referenced from LibraryBulkBar / StrategyDetailPanel later:
export { formatCurrency, formatPercentage }
