import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { SectionLabel } from '@/components/layout'
import { DataTable, EmptyState } from '@/components/primitives'
import { Sprout } from 'lucide-react'
import { cn, formatNumber, formatPercentage } from '@/lib/utils'
import type { StrategyAttribution } from '../useResearchData'

interface PerStrategyAttributionTableProps {
  rows: StrategyAttribution[] | undefined
  loading?: boolean
  onRowClick?: (row: StrategyAttribution) => void
  activeStrategyId?: string | null
}

export function PerStrategyAttributionTable({
  rows,
  loading,
  onRowClick,
  activeStrategyId,
}: PerStrategyAttributionTableProps) {
  const data = rows ?? []

  const maxContribution = useMemo(
    () =>
      data.reduce((m, r) => Math.max(m, Math.abs(r.contribution_percent)), 0) || 1,
    [data],
  )

  const columns = useMemo<ColumnDef<StrategyAttribution>[]>(
    () => [
      {
        id: 'strategy_name',
        accessorKey: 'strategy_name',
        header: () => <span>Strategy</span>,
        size: 260,
        cell: ({ getValue }) => (
          <span className="truncate" title={String(getValue())}>
            {String(getValue())}
          </span>
        ),
      },
      {
        id: 'total_return',
        accessorKey: 'total_return',
        header: () => <span className="text-right block w-full">Return</span>,
        size: 90,
        cell: ({ getValue }) => {
          const v = Number(getValue())
          return (
            <span
              className={cn(
                'mono tabular-nums text-right block',
                v > 0 ? 'text-[var(--pnl-up)]' : v < 0 ? 'text-[var(--pnl-down)]' : '',
              )}
            >
              {formatPercentage(v)}
            </span>
          )
        },
      },
      {
        id: 'contribution_percent',
        accessorKey: 'contribution_percent',
        header: () => <span className="block w-full">Contribution</span>,
        size: 200,
        cell: ({ getValue }) => {
          const v = Number(getValue())
          const pct = Math.min(100, (Math.abs(v) / maxContribution) * 100)
          return (
            <div className="flex items-center gap-2">
              <div className="h-1.5 flex-1 min-w-[80px] bg-[var(--bg-2)] rounded-[1px] overflow-hidden relative">
                <div
                  className="absolute inset-y-0"
                  style={{
                    width: `${pct}%`,
                    backgroundColor: v >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)',
                    left: v >= 0 ? '50%' : `${50 - pct}%`,
                  }}
                />
                <div
                  className="absolute inset-y-0"
                  style={{ left: '50%', width: 1, backgroundColor: 'var(--border-subtle)' }}
                />
              </div>
              <span
                className={cn(
                  'mono tabular-nums text-[10px] w-14 text-right',
                  v > 0
                    ? 'text-[var(--pnl-up)]'
                    : v < 0
                      ? 'text-[var(--pnl-down)]'
                      : 'text-[var(--text-2)]',
                )}
              >
                {formatNumber(v, 1)}%
              </span>
            </div>
          )
        },
      },
      {
        id: 'sharpe_ratio',
        accessorKey: 'sharpe_ratio',
        header: () => <span className="text-right block w-full">Sharpe</span>,
        size: 70,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums text-right block">
            {formatNumber(Number(getValue()), 2)}
          </span>
        ),
      },
      {
        id: 'total_trades',
        accessorKey: 'total_trades',
        header: () => <span className="text-right block w-full">Trades</span>,
        size: 60,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums text-right block">
            {formatNumber(Number(getValue()), 0)}
          </span>
        ),
      },
      {
        id: 'win_rate',
        accessorKey: 'win_rate',
        header: () => <span className="text-right block w-full">Win %</span>,
        size: 65,
        cell: ({ getValue }) => {
          const v = Number(getValue())
          return (
            <span className="mono tabular-nums text-right block">
              {formatNumber(v, 1)}%
            </span>
          )
        },
      },
    ],
    [maxContribution],
  )

  const totalRetSum = data.reduce((a, r) => a + r.total_return, 0)

  return (
    <section className="space-y-1.5">
      <SectionLabel
        actions={
          <span className="text-[10px] normal-case tracking-normal text-[var(--text-3)]">
            {data.length} strategies · Σ return = {formatPercentage(totalRetSum)}
          </span>
        }
      >
        Per-strategy attribution
      </SectionLabel>
      {data.length === 0 && !loading ? (
        <EmptyState
          icon={Sprout}
          title="No strategy attribution yet"
          description="Shows once at least one strategy has positions in the selected period."
          className="py-8"
        />
      ) : (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] max-h-[340px]">
          <DataTable
            data={data}
            columns={columns}
            rowKey={(r) => r.strategy_id}
            loading={loading}
            density="default"
            onRowClick={onRowClick}
            activeRowId={activeStrategyId}
          />
        </div>
      )}
    </section>
  )
}
