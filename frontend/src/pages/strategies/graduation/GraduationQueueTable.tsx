import { useMemo } from 'react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { GraduationCap } from 'lucide-react'
import {
  DataTable,
  EmptyState,
} from '@/components/primitives'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { formatTimestamp } from '@/lib/utils'
import type { GraduationQueueRow } from '../useStrategiesData'

interface GraduationQueueTableProps {
  queue: GraduationQueueRow[]
  loading?: boolean
  selectedKey: string | null
  onSelect: (row: GraduationQueueRow) => void
  sorting: SortingState
  onSortingChange: React.Dispatch<React.SetStateAction<SortingState>>
}

/**
 * GraduationQueueTable — all PAPER (template, symbol) pairs with ≥20 trades
 * that cleared qualification. Sorted by qualification_ratio desc by default.
 */
export function GraduationQueueTable({
  queue,
  loading,
  selectedKey,
  onSelect,
  sorting,
  onSortingChange,
}: GraduationQueueTableProps) {
  const columns = useMemo<ColumnDef<GraduationQueueRow>[]>(
    () => [
      {
        id: 'template',
        header: () => 'Template',
        accessorFn: (r) => r.template_name ?? r.strategy_name,
        size: 260,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span
              className="text-[var(--text-0)] font-medium truncate max-w-[240px]"
              title={row.original.template_name ?? row.original.strategy_name}
            >
              {row.original.template_name ?? row.original.strategy_name}
            </span>
            <span
              className="text-[9px] text-[var(--text-3)] truncate max-w-[240px]"
              title={row.original.strategy_name}
            >
              {row.original.strategy_name}
            </span>
          </div>
        ),
      },
      {
        id: 'symbol',
        header: () => 'Symbol',
        accessorKey: 'symbol',
        size: 80,
        cell: ({ row }) => (
          <span className="mono text-[var(--text-0)] font-medium">
            {row.original.symbol}
          </span>
        ),
      },
      {
        id: 'paper_trades',
        header: () => 'Trades',
        accessorKey: 'paper_trades',
        size: 76,
        cell: ({ row }) => (
          <span className="mono tabular-nums text-[var(--text-1)]">
            {row.original.paper_trades}
          </span>
        ),
      },
      {
        id: 'paper_sharpe',
        header: () => 'Paper Sh.',
        accessorFn: (r) => r.paper_sharpe ?? null,
        size: 88,
        cell: ({ row }) => {
          const s = row.original.paper_sharpe
          if (s == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          const color =
            s >= 1.5
              ? 'var(--pnl-up)'
              : s >= 1.0
                ? 'var(--text-0)'
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
        id: 'wf_sharpe',
        header: () => 'WF Sh.',
        accessorFn: (r) => r.wf_sharpe ?? null,
        size: 80,
        cell: ({ row }) => {
          const s = row.original.wf_sharpe
          if (s == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <span className="mono tabular-nums text-[var(--text-2)]">
              {s.toFixed(2)}
            </span>
          )
        },
      },
      {
        id: 'qualification_ratio',
        header: () => 'Q-ratio',
        accessorFn: (r) => r.qualification_ratio ?? null,
        size: 96,
        cell: ({ row }) => {
          const r = row.original.qualification_ratio
          if (r == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          const color =
            r >= 1.0
              ? 'var(--pnl-up)'
              : r >= 0.8
                ? 'var(--text-0)'
                : r >= 0.6
                  ? 'var(--status-warning)'
                  : 'var(--pnl-down)'
          return (
            <span className="mono tabular-nums" style={{ color }}>
              {(r * 100).toFixed(0)}%
            </span>
          )
        },
      },
      {
        id: 'paper_win_rate',
        header: () => 'Win %',
        accessorFn: (r) => r.paper_win_rate ?? null,
        size: 80,
        cell: ({ row }) => {
          const wr = row.original.paper_win_rate
          if (wr == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <span className="mono tabular-nums text-[var(--text-1)]">
              {(wr * 100).toFixed(0)}%
            </span>
          )
        },
      },
      {
        id: 'paper_total_pnl',
        header: () => 'Paper P&L',
        accessorFn: (r) => r.paper_total_pnl ?? null,
        size: 108,
        cell: ({ row }) => {
          const p = row.original.paper_total_pnl
          if (p == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <PnLNumber value={p} format="currency" precision={0} size="sm" showSign />
          )
        },
      },
      {
        id: 'first_paper_trade',
        header: () => 'Since',
        accessorKey: 'first_paper_trade',
        size: 120,
        cell: ({ row }) => (
          <span className="text-[10px] text-[var(--text-3)]">
            {formatTimestamp(row.original.first_paper_trade, 'short') || '—'}
          </span>
        ),
      },
    ],
    [],
  )

  if (!loading && queue.length === 0) {
    return (
      <EmptyState
        icon={GraduationCap}
        title="Graduation queue is empty"
        description="Pairs qualify with ≥15 paper trades, paper Sharpe between 60%–200% of WF Sharpe, win rate ≥ 55%, and positive P&L. Open the Library and filter to graduation-eligible to see the paper pool."
        action={
          <a
            className="text-[var(--accent-primary)] text-[11px] hover:underline"
            href="/strategies/library?pills=graduation-eligible"
          >
            View paper-eligible strategies →
          </a>
        }
      />
    )
  }

  return (
    <DataTable
      data={queue}
      columns={columns}
      rowKey={(r) => `${r.strategy_id}::${r.symbol}`}
      loading={loading}
      sorting={{ state: sorting, onChange: onSortingChange }}
      density="compact"
      onRowClick={(r) => onSelect(r)}
      activeRowId={selectedKey}
    />
  )
}
