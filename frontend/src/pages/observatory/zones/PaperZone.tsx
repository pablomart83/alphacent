import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { DataTable, StatTile, EmptyState } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { ConvictionBar } from '@/components/trading/ConvictionBar'
import { formatNumber, formatPercentage } from '@/lib/utils'
import {
  useApproachingGraduation,
  type ApproachingGraduationRow,
} from '@/pages/strategies/useStrategiesData'

/**
 * PAPER (DEMO) — the data-collection sandbox. The goal here is breadth of
 * graduation-quality trades, so we surface the approaching-graduation queue and
 * paper quality stats. Always DEMO-scoped (paper trades live on the demo book).
 */
export function PaperZone() {
  const approaching = useApproachingGraduation(5, 40)
  const rows = approaching.data?.approaching ?? []

  const nearGraduation = rows.filter((r) => r.graduation_score >= 80).length
  const avgScore =
    rows.length > 0 ? rows.reduce((s, r) => s + r.graduation_score, 0) / rows.length : null

  const columns = useMemo<ColumnDef<ApproachingGraduationRow, unknown>[]>(
    () => [
      {
        header: 'Symbol',
        accessorKey: 'symbol',
        cell: (c) => <span className="mono font-medium text-[var(--text-0)]">{c.row.original.symbol}</span>,
      },
      {
        header: 'Template',
        accessorKey: 'template_name',
        cell: (c) => (
          <span className="text-[var(--text-2)] truncate block max-w-[180px]" title={c.row.original.template_name}>
            {c.row.original.template_name}
          </span>
        ),
      },
      { header: 'Trades', accessorKey: 'trades', cell: (c) => <span className="mono">{c.row.original.trades}</span> },
      {
        header: 'Sharpe',
        accessorKey: 'sharpe',
        cell: (c) => <span className="mono">{formatNumber(c.row.original.sharpe, 2)}</span>,
      },
      {
        header: 'Win %',
        accessorKey: 'win_rate',
        cell: (c) => <span className="mono">{formatPercentage(c.row.original.win_rate, { precision: 0, signed: false })}</span>,
      },
      {
        header: 'P&L',
        accessorKey: 'total_pnl',
        cell: (c) => <PnLNumber value={c.row.original.total_pnl} format="currency" precision={0} size="sm" />,
      },
      {
        header: 'Grad score',
        accessorKey: 'graduation_score',
        cell: (c) => (
          <div className="w-[92px]">
            <ConvictionBar score={c.row.original.graduation_score} size="mini" showValue />
          </div>
        ),
      },
    ],
    [],
  )

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-2">
        <StatTile label="Approaching (≥5 trades)" value={approaching.isLoading ? '…' : rows.length} tone="info" />
        <StatTile
          label="Near graduation (≥80)"
          value={approaching.isLoading ? '…' : nearGraduation}
          tone={nearGraduation > 0 ? 'up' : 'default'}
          pulseValue={nearGraduation > 0}
        />
        <StatTile label="Avg grad score" value={avgScore == null ? '—' : formatNumber(avgScore, 0)} />
      </div>

      <div>
        <SectionLabel>Approaching graduation queue · DEMO</SectionLabel>
        <div className="h-[280px] rounded-[3px] border border-[var(--border-subtle)] overflow-hidden">
          <DataTable
            data={rows}
            columns={columns}
            rowKey={(r) => `${r.template_name}:${r.symbol}`}
            density="compact"
            loading={approaching.isLoading}
            stackBelow="md"
            emptyState={
              <EmptyState title="No strategies approaching graduation" description="Paper strategies need ≥5 trades to appear here." />
            }
            mobileCard={(r) => (
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="mono font-semibold text-[var(--text-0)]">{r.symbol}</span>
                  <div className="w-[92px]">
                    <ConvictionBar score={r.graduation_score} size="mini" showValue />
                  </div>
                </div>
                <div className="text-[10px] text-[var(--text-2)] truncate">{r.template_name}</div>
                <div className="flex gap-3 text-[10px] mono text-[var(--text-1)]">
                  <span>{r.trades} tr</span>
                  <span>Sh {formatNumber(r.sharpe, 2)}</span>
                  <span>{formatPercentage(r.win_rate, { precision: 0, signed: false })} WR</span>
                  <PnLNumber value={r.total_pnl} format="currency" precision={0} size="sm" />
                </div>
              </div>
            )}
          />
        </div>
      </div>
    </div>
  )
}
