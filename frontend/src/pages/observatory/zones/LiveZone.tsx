import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { DataTable, StatTile, EmptyState } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { formatCurrency, formatNumber, formatPercentage } from '@/lib/utils'
import { RiskScoreHero } from '@/pages/guard/RiskScoreHero'
import { RiskMetricTiles } from '@/pages/guard/RiskMetricTiles'
import { LiveTradingHealthCard } from '@/pages/guard/LiveTradingHealthCard'
import { useRiskMetrics, useRiskLimits } from '@/pages/guard/useGuardData'
import { useExecutionQuality, useOpenPositions, type PositionRow } from '@/pages/book/useBookData'

/**
 * LIVE — real-capital alpha under risk discipline. Pinned to the LIVE account
 * (never follows the global toggle) so the live book is never mixed with demo,
 * per the eToro shared-position-id caveat in steering. Read-only: the kill
 * switch stays on Guard; here we only show live health + risk + TCA.
 */
export function LiveZone() {
  const risk = useRiskMetrics('LIVE')
  const riskLimits = useRiskLimits('LIVE')
  const tca = useExecutionQuality('1M', 'LIVE')
  const positions = useOpenPositions('LIVE')

  const posRows = positions.data?.positions ?? []
  const q = tca.data

  const columns = useMemo<ColumnDef<PositionRow, unknown>[]>(
    () => [
      {
        header: 'Symbol',
        accessorKey: 'symbol',
        cell: (c) => <span className="mono font-medium text-[var(--text-0)]">{c.row.original.symbol}</span>,
      },
      {
        header: 'Side',
        accessorKey: 'side',
        cell: (c) => (
          <span
            className="text-[10px] uppercase font-semibold"
            style={{ color: c.row.original.side?.toUpperCase() === 'SELL' ? 'var(--pnl-down)' : 'var(--pnl-up)' }}
          >
            {c.row.original.side}
          </span>
        ),
      },
      {
        header: 'Entry',
        accessorKey: 'entry_price',
        cell: (c) => <span className="mono">{formatNumber(c.row.original.entry_price, 2)}</span>,
      },
      {
        header: 'Last',
        accessorKey: 'current_price',
        cell: (c) => <span className="mono">{formatNumber(c.row.original.current_price, 2)}</span>,
      },
      {
        header: 'uP&L',
        accessorKey: 'unrealized_pnl',
        cell: (c) => <PnLNumber value={c.row.original.unrealized_pnl} format="currency" precision={0} size="sm" />,
      },
      {
        header: 'uP&L %',
        accessorKey: 'unrealized_pnl_percent',
        cell: (c) => <PnLNumber value={c.row.original.unrealized_pnl_percent} format="percentage" precision={1} size="sm" />,
      },
    ],
    [],
  )

  return (
    <div className="space-y-2">
      {/* Live health + risk score */}
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        <LiveTradingHealthCard />
        <RiskScoreHero metrics={risk.data} loading={risk.isLoading} />
      </div>

      <RiskMetricTiles metrics={risk.data} limits={riskLimits.data} loading={risk.isLoading || riskLimits.isLoading} />

      {/* TCA / execution quality */}
      <div>
        <SectionLabel>Execution quality · TCA (1M, LIVE)</SectionLabel>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
          <StatTile
            label="Avg slippage"
            value={q?.avg_slippage == null ? '—' : `${formatNumber(q.avg_slippage, 1)} bps`}
            tone={q?.avg_slippage != null && q.avg_slippage > 10 ? 'warn' : 'default'}
          />
          <StatTile
            label="Fill rate"
            value={q?.fill_rate == null ? '—' : formatPercentage(q.fill_rate, { precision: 0, signed: false })}
            tone={q?.fill_rate != null && q.fill_rate < 90 ? 'warn' : 'up'}
          />
          <StatTile
            label="Avg fill time"
            value={q?.avg_fill_time_seconds == null ? '—' : `${formatNumber(q.avg_fill_time_seconds, 0)}s`}
          />
          <StatTile
            label="Rejection rate"
            value={q?.rejection_rate == null ? '—' : formatPercentage(q.rejection_rate, { precision: 0, signed: false })}
            tone={q?.rejection_rate != null && q.rejection_rate > 5 ? 'down' : 'default'}
          />
          <StatTile
            label="Orders (filled)"
            value={q == null ? '—' : `${q.filled_orders}/${q.total_orders}`}
          />
        </div>
      </div>

      {/* Open live positions */}
      <div>
        <SectionLabel>Open live positions ({posRows.length})</SectionLabel>
        <div className="max-h-[320px] rounded-[3px] border border-[var(--border-subtle)] overflow-hidden">
          <DataTable
            data={posRows}
            columns={columns}
            rowKey={(r) => r.id}
            density="compact"
            loading={positions.isLoading}
            stackBelow="md"
            emptyState={<EmptyState title="No open live positions" description="The live book is currently flat." />}
            mobileCard={(r) => (
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="mono font-semibold text-[var(--text-0)]">{r.symbol}</span>
                  <span
                    className="text-[10px] uppercase font-semibold"
                    style={{ color: r.side?.toUpperCase() === 'SELL' ? 'var(--pnl-down)' : 'var(--pnl-up)' }}
                  >
                    {r.side}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[10px] mono text-[var(--text-1)]">
                  <span>{formatCurrency(r.entry_price, { precision: 2 })} → {formatCurrency(r.current_price, { precision: 2 })}</span>
                  <PnLNumber value={r.unrealized_pnl_percent} format="percentage" precision={1} size="sm" />
                </div>
              </div>
            )}
          />
        </div>
      </div>
    </div>
  )
}
